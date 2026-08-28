"""ISOLATED ML experiment — plots. Writes PNGs ONLY into ml_revenue_experiment/outputs/."""
from __future__ import annotations
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def actual_vs_predicted(P, hw_col, a_col, b_col, labels, out):
    fig,ax=plt.subplots(figsize=(9,4.5))
    ax.plot(P["period"],P["actual"],marker="o",color="#222",label="Actual")
    ax.plot(P["period"],P[hw_col],marker="s",color="#1f77b4",label="Holt-Winters (existing)")
    ax.plot(P["period"],P[a_col],marker="^",color="#2ca02c",label=labels[0])
    ax.plot(P["period"],P[b_col],marker="v",color="#d62728",label=labels[1])
    ax.set_title("Actual vs predicted revenue (unseen test)"); ax.set_ylabel("Revenue")
    ax.tick_params(axis="x",rotation=45); ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(os.path.join(out,"ml_revenue_experiment_actual_vs_predicted.png"),dpi=110); plt.close(fig)

def errors_over_time(ea, out):
    fig,ax=plt.subplots(figsize=(9,4))
    ax.bar(ea["period"],ea["abs_error"],color="#d62728",alpha=0.8)
    ax.set_title("Absolute error over time (best Experiment B)"); ax.set_ylabel("|actual - pred|")
    ax.tick_params(axis="x",rotation=45); fig.tight_layout()
    fig.savefig(os.path.join(out,"ml_revenue_experiment_errors.png"),dpi=110); plt.close(fig)

def error_by_occupancy(ea, out):
    g=ea.groupby("occupancy_bucket",observed=False)["abs_error"].mean()
    fig,ax=plt.subplots(figsize=(6,4))
    ax.bar(g.index.astype(str),g.values,color="#ff7f0e")
    ax.set_title("Mean absolute error by occupancy level"); ax.set_ylabel("mean |error|")
    fig.tight_layout(); fig.savefig(os.path.join(out,"ml_revenue_experiment_error_by_occupancy.png"),dpi=110); plt.close(fig)

def scatter_actual_pred(P, col, label, out):
    fig,ax=plt.subplots(figsize=(5,5))
    ax.scatter(P["actual"],P[col],color="#d62728")
    lo=min(P["actual"].min(),P[col].min()); hi=max(P["actual"].max(),P[col].max())
    ax.plot([lo,hi],[lo,hi],"--",color="#888")
    ax.set_xlabel("Actual"); ax.set_ylabel(f"Predicted ({label})"); ax.set_title("Actual vs predicted (scatter)")
    fig.tight_layout(); fig.savefig(os.path.join(out,"ml_revenue_experiment_scatter.png"),dpi=110); plt.close(fig)
