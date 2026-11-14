"""Location-aware crop rotation ranking adapted from the repository's data_science_tsuyu branch.

Uses NASA POWER daily parameters, FAO-56-style ET0 calculation, SoilGrids surface
soil observations, crop-family constraints and transparent impact indicators.
The data contain approximate regional agronomic parameters and proxy economics;
not a calibrated farm recommendation or yield forecast.
"""
from __future__ import annotations

import json
import math
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

CROPS_PATH = Path(__file__).resolve().parents[3] / "data" / "rotation-crops.json"
EROSION = {"perennial_forage_legume":1.0,"cover_crop":0.9,"cash_grain":0.5,"cash_grain_legume":0.3}

CROP_ALIASES = {
    "corn": "maize",
    "maize": "maize",
    "wheat": "winter_wheat",
    "winter_wheat": "winter_wheat",
    "soybeans": "soybean",
    "soybean": "soybean",
    "soy": "soybean",
    "maize_corn": "maize",
}


def normalize_crop_name(name: str) -> str:
    if not isinstance(name, str):
        return name
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    key = key.replace("/", "_")
    return CROP_ALIASES.get(key, key)


def crops_catalogue() -> dict:
    return {k:v for k,v in json.loads(CROPS_PATH.read_text()).items() if not k.startswith('_')}


def weather_frame(parameters: dict) -> pd.DataFrame:
    df = pd.DataFrame(parameters)
    df.index = pd.to_datetime(df.index,format='%Y%m%d',errors='coerce')
    df = df.apply(pd.to_numeric,errors='coerce').replace(-999,np.nan).dropna(how='all')
    return df.sort_index()


def et0_penman_monteith(df: pd.DataFrame, latitude: float) -> pd.Series:
    """FAO-56 Penman-Monteith daily reference ET0 adapted from Tsuyu's engine."""
    tmax,tmin,t,rh,u2,rs=(df[x].astype(float) for x in ('T2M_MAX','T2M_MIN','T2M','RH2M','WS2M','ALLSKY_SFC_SW_DWN'))
    elev=300.0  # assumed altitude; local elevation not provided
    pressure=101.3*((293-0.0065*elev)/293)**5.26
    gamma=0.000665*pressure
    sat=lambda z:0.6108*np.exp(17.27*z/(z+237.3))
    es=(sat(tmax)+sat(tmin))/2;ea=sat(t)*rh/100
    delta=4098*sat(t)/(t+237.3)**2
    day=df.index.dayofyear.to_numpy()
    phi=np.radians(latitude)
    dr=1+0.033*np.cos(2*np.pi/365*day)
    decl=0.409*np.sin(2*np.pi/365*day-1.39)
    ws=np.arccos(np.clip(-np.tan(phi)*np.tan(decl),-1,1))
    ra=(24*60/np.pi)*0.0820*dr*(ws*np.sin(phi)*np.sin(decl)+np.cos(phi)*np.cos(decl)*np.sin(ws))
    rso=(0.75+2e-5*elev)*ra
    rns=0.77*rs
    rnl=4.903e-9*((tmax+273.16)**4+(tmin+273.16)**4)/2*(0.34-0.14*np.sqrt(ea.clip(lower=0)))*(1.35*(rs/rso).clip(upper=1.0)-0.35)
    result=(0.408*delta*(rns-rnl)+gamma*(900/(t+273))*u2*(es-ea))/(delta+gamma*(1+0.34*u2))
    return result.clip(lower=0).replace([np.inf,-np.inf],np.nan)


def best_window(df: pd.DataFrame,crop: dict):
    temps=df['T2M'].dropna()
    length=crop['season_length_days'];middle=(crop['min_temp_c']+crop['max_temp_c'])/2
    if len(temps)<length:return float(temps.mean()),None
    rolling=temps.rolling(length).mean().dropna()
    if rolling.empty:return float(temps.mean()),None
    idx=(rolling-middle).abs().idxmin()
    return float(rolling.loc[idx]),idx


def et_demand(et0: pd.Series,crop: dict):
    n=min(len(et0),crop['season_length_days'])
    if n<10:return float('nan')
    a=max(1,round(n*0.2));b=max(1,round(n*0.4));c=max(0,n-a-b)
    kc=np.concatenate([np.full(a,crop['kc_ini']),np.linspace(crop['kc_ini'],crop['kc_mid'],b),np.linspace(crop['kc_mid'],crop['kc_end'],c)])[:n]
    return float(np.nansum(et0.iloc[:n].to_numpy()*kc))


def passes_rules(seq: tuple[dict,...]):
    return all(seq[i]['crop_family']!=seq[i-1]['crop_family'] for i in range(1,len(seq)))


def score_rotation(sequence: list[dict], baseline: dict, demand: dict, weights: dict) -> dict:
    tot=sum(weights.values())
    weights={k:v/tot for k,v in weights.items()}
    rows=[]
    for i,c in enumerate(sequence):
        previous=sequence[i-1] if i else None
        n_score=np.tanh(max(0,c['nitrogen_balance_kg_ha'])/100)
        carbon=0.5 if baseline['soil_carbon_is_estimated'] else max(0,min(1,1-baseline['soc_g_kg']/15))
        depth_bonus=1.0 if previous and previous['root_depth_class']!=c['root_depth_class'] else 0.0
        eros=min(1,EROSION.get(c['role'],0.5)+(0.1 if c['root_type'].startswith('fibrous') else 0))
        soil=float(np.clip(0.35*n_score+0.25*carbon+0.15*depth_bonus+0.25*eros,0,1))
        water_need=demand[c['_name']]
        available=baseline['precip_mm']*(0.5+0.5*baseline['root_wetness'])
        water=max(0,min(1,1-max(water_need-available,0)/max(water_need,1)))
        resil={'low':0.2,'medium':0.6,'high':1.0}.get(c['drought_tolerance'],0.5)
        revenue=0 if not c['has_market_revenue'] else math.tanh((c['typical_yield_t_ha'] or 0)/8)
        year_score=sum(weights[k]*v for k,v in [('soil',soil),('water',water),('resilience',resil),('revenue',revenue)])
        rows.append({'crop':c['_name'],'soil_score':round(soil,3),'water_score':round(water,3),'resilience_score':round(resil,3),'revenue_score':round(revenue,3),'year_score':round(year_score,3),'bare_field_days':max(0,365-c['season_length_days']),'explanation':{'nitrogen_balance_kg_ha':c['nitrogen_balance_kg_ha'],'water_demand_mm':round(water_need,1),'water_deficit_mm':round(max(water_need-available,0),1),'drought_tolerance':c['drought_tolerance'],'erosion_protection_score':round(eros,2),'revenue_is_yield_proxy':True}})
    return {'sequence':[c['_name'] for c in sequence], 'rsi':round(sum(0.9**i*row['year_score'] for i,row in enumerate(rows)),3),'year_breakdown':rows}


def impacts(seq: list[dict],demand: dict,baseline_crop: dict):
    total=len(seq)
    n=sum(c['nitrogen_balance_kg_ha'] for c in seq)-total*baseline_crop['nitrogen_balance_kg_ha']
    w=total*demand[baseline_crop['_name']]-sum(demand[c['_name']] for c in seq)
    bare=total*(365-baseline_crop['season_length_days'])-sum(365-c['season_length_days'] for c in seq)
    return {'baseline':'continuous maize','nitrogen_fertilizer_avoided_kg_ha':round(n,1),'water_saved_mm':round(w,1),'water_saved_pct':round(100*w/max(1,total*demand[baseline_crop['_name']]),1),'bare_field_days_avoided':bare,
            'sdg_tags':[{'sdg':'SDG 6','label':'Clean Water and Sanitation'} for _ in [0] if w>0]+[{'sdg':'SDG 13','label':'Climate Action'} for _ in [0] if n>0]+[{'sdg':'SDG 15','label':'Life on Land'} for _ in [0] if bare>0]}


def rank_rotations(weather_parameters: dict, soil: dict,latitude: float, sequence_length:int=3, top_n:int=5,weights:dict|None=None,current_rotation:list[str]|None=None):
    weights=weights or {'soil':0.3,'water':0.3,'resilience':0.15,'revenue':0.25}
    if any(not np.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())<=0:
        raise ValueError('Priority weights must be nonnegative and not all zero')
    df=weather_frame(weather_parameters)
    required=['T2M','T2M_MIN','T2M_MAX','RH2M','WS2M','ALLSKY_SFC_SW_DWN','PRECTOTCORR','GWETROOT']
    if len(df)<100 or any(k not in df for k in required):
        raise ValueError('Insufficient NASA POWER data to rank growing seasons')
    daily=et0_penman_monteith(df,latitude)
    catalogue=crops_catalogue()
    suitable={};excluded=[]
    for key,c in catalogue.items():
        temp,idx=best_window(df,c)
        if c['min_temp_c']<=temp<=c['max_temp_c']:
            suitable[key]={**c,'_name':key}
        else:excluded.append({'crop':key,'site_mean_temp_c':round(temp,1),'crop_temp_tolerance_c':[c['min_temp_c'],c['max_temp_c']]})
    if not suitable: raise ValueError('No climate-compatible crop candidates found in this sample catalogue')
    demand={k:et_demand(daily,v) for k,v in catalogue.items()}
    if any(not np.isfinite(demand[k]) for k in suitable):raise ValueError('Insufficient radiation/weather samples to calculate water demand')
    baseline={'precip_mm':float(df['PRECTOTCORR'].sum()),'root_wetness':float(df['GWETROOT'].dropna().mean()),'soc_g_kg':soil.get('soc_g_kg') or 15.0,'soil_carbon_is_estimated':soil.get('soc_g_kg') is None}
    if not np.isfinite(baseline['root_wetness']):raise ValueError('Soil root wetness not available')
    maize={**catalogue['maize'],'_name':'maize'}
    ranked=[]
    for tup in product(suitable.values(),repeat=sequence_length):
        if not passes_rules(tup):continue
        seq=list(tup)
        result=score_rotation(seq,baseline,demand,weights)
        result['impact_metrics']=impacts(seq,demand,maize)
        gaps=['Temperature-only climate filter; precipitation timing, day length and pest pressure not fully modelled.','Revenue is a yield proxy, not actual profit; erosion is a qualitative indicator, not a field erosion model.','Bare-field days omit crop residue, follow-on cover crops and specific planting dates.']
        if baseline['soil_carbon_is_estimated']:gaps.append('Soil carbon unavailable; a neutral estimate was used. Test local soil before decisions.')
        if any(c.get('flood_irrigated') for c in seq):gaps.append('Rice water use excludes standing-water/percolation losses and may be substantially understated.')
        if any(c['role']=='perennial_forage_legume' for c in seq):gaps.append('Perennial alfalfa is not realistically replanted every year; multi-year management is not modelled.')
        result['risks_and_gaps']=gaps
        ranked.append(result)
    ranked.sort(key=lambda x:x['rsi'],reverse=True)
    current=None
    if current_rotation:
        normalized=[normalize_crop_name(k) for k in current_rotation]
        unknown=[k for k in normalized if k not in catalogue]
        if unknown:raise ValueError('Unknown current rotation crops: '+', '.join(unknown))
        seq=[{**catalogue[k],'_name':k} for k in normalized]
        current=score_rotation(seq,baseline,demand,weights)
        current['impact_metrics']=impacts(seq,demand,maize)
        current['risks_and_gaps']=['Current practice is shown for comparison even if it violates the crop-family gap rule.']
    return {'soil':soil,'mean_et0_mm_day':round(float(daily.mean()),3),'top_rotations':ranked[:top_n],'excluded_crops':excluded,'current_rotation':current,'note':'Historical NASA POWER gridded weather + SoilGrids point estimates. Scoring is an educational model, not a forecast, economic profit estimate or local field diagnosis.'}
