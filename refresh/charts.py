#!/usr/bin/env python3
"""Briefing charts for the Investment Tracker refresh.

Extracted unchanged from snapshot.py's build_charts (the retired sheet
script); refresh_db.py imports build_charts from here now. Same four
charts, same filenames, written to <REFRESH_BASE>/charts/ (REFRESH_BASE
defaults to this directory):
  allocation.png, value_by_ticker.png, gain_loss.png, graham.png
"""
import os

BASE = os.environ.get(
    "REFRESH_BASE", os.path.dirname(os.path.abspath(__file__)))


def build_charts(positions):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts = os.path.join(BASE, "charts")
    os.makedirs(charts, exist_ok=True)

    tickers = [p["ticker"] for p in positions]
    values = [p["value"] for p in positions]

    # 1. Allocation by ticker (pie)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(values, labels=tickers, autopct="%1.0f%%", startangle=90)
    ax.set_title("Portfolio allocation by holding")
    fig.tight_layout()
    fig.savefig(os.path.join(charts, "allocation.png"), dpi=110)
    plt.close(fig)

    # 2. Current value by ticker (bar)
    order = sorted(range(len(tickers)), key=lambda i: values[i], reverse=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([tickers[i] for i in order], [values[i] for i in order])
    ax.set_title("Current value by holding ($)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(os.path.join(charts, "value_by_ticker.png"), dpi=110)
    plt.close(fig)

    # 3. Gain/loss by ticker (bar)
    gains = [p["gain"] for p in positions]
    order = sorted(range(len(tickers)), key=lambda i: gains[i], reverse=True)
    colors = ["#2ca02c" if gains[i] >= 0 else "#d62728" for i in order]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([tickers[i] for i in order], [gains[i] for i in order], color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Gain / loss by holding ($)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(os.path.join(charts, "gain_loss.png"), dpi=110)
    plt.close(fig)

    # 4. Price vs Graham number (stocks only)
    stocks = [p for p in positions if p["graham"] and p["price"]]
    if stocks:
        labels = [p["ticker"] for p in stocks]
        x = range(len(labels))
        fig, ax = plt.subplots(figsize=(8, 4.5))
        w = 0.35
        ax.bar([i - w / 2 for i in x], [p["price"] for p in stocks],
               width=w, label="Price")
        ax.bar([i + w / 2 for i in x], [p["graham"] for p in stocks],
               width=w, label="Graham number")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=30)
        ax.set_title("Price vs Graham number (below Graham = potential value)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(charts, "graham.png"), dpi=110)
        plt.close(fig)
