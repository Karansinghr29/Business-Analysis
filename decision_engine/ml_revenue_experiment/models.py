"""ISOLATED ML experiment — model factory (fixed seeds, conservative complexity for ~30 monthly obs)."""
from __future__ import annotations
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor

def make_models():
    return {
      "LinearRegression": LinearRegression(),
      "RandomForest":     RandomForestRegressor(n_estimators=200,max_depth=3,min_samples_leaf=2,random_state=0,n_jobs=1),
      "XGBoost":          XGBRegressor(n_estimators=120,max_depth=3,learning_rate=0.1,subsample=1.0,
                                       colsample_bytree=1.0,random_state=0,n_jobs=1,verbosity=0),
      "LightGBM":         LGBMRegressor(n_estimators=120,max_depth=3,num_leaves=7,min_child_samples=3,
                                        random_state=0,n_jobs=1,verbose=-1,deterministic=True,force_row_wise=True),
    }
