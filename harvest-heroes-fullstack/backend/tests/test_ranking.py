from datetime import date, timedelta

import numpy as np
import pandas as pd
from app.engine.ranking import rank_rotations, et0_penman_monteith, crops_catalogue


def mock_historical_nasa_power(days=370):
    """Test-only synthetic weather. The application does not serve these as observations."""
    start=date(2025,1,1)
    out={k:{} for k in ('T2M','T2M_MIN','T2M_MAX','RH2M','WS2M','ALLSKY_SFC_SW_DWN','PRECTOTCORR','GWETROOT')}
    for i in range(days):
        day=(start+timedelta(days=i)).strftime('%Y%m%d')
        t=17+8*np.sin(i*2*np.pi/365)
        for key,value in {'T2M':t,'T2M_MIN':t-5,'T2M_MAX':t+5,'RH2M':60,'WS2M':2,'ALLSKY_SFC_SW_DWN':18,'PRECTOTCORR':2.8,'GWETROOT':0.45}.items():
            out[key][day]=float(value)
    return out


def test_tsuyu_style_rotation_scoring_with_synthetic_weather():
    soil={'soc_g_kg':17,'ph':6.2,'clay_pct':24,'sand_pct':34,'source':'Synthetic test only'}
    result=rank_rotations(mock_historical_nasa_power(),soil,42.0,sequence_length=3,top_n=5,current_rotation=['maize','soybean','maize'])
    assert result['top_rotations']
    assert len(result['top_rotations'])<=5
    assert result['top_rotations'][0]['rsi']>=result['top_rotations'][-1]['rsi']
    for entry in result['top_rotations']:
        assert len(entry['sequence'])==3
        fam=[crops_catalogue()[c]['crop_family'] for c in entry['sequence']]
        assert all(fam[i]!=fam[i-1] for i in range(1,3))
        assert 'water_saved_mm' in entry['impact_metrics']
    assert result['current_rotation']['sequence']==['maize','soybean','maize']
    assert result['mean_et0_mm_day']>0


def test_rotation_rank_accepts_frontend_crop_aliases():
    soil={'soc_g_kg':17,'ph':6.2,'clay_pct':24,'sand_pct':34,'source':'Synthetic test only'}
    result=rank_rotations(mock_historical_nasa_power(),soil,42.0,sequence_length=3,top_n=2,current_rotation=['corn','soybeans','wheat'])
    assert result['current_rotation']['sequence']==['maize','soybean','winter_wheat']
