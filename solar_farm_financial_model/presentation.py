"""Presentation helpers for the Solar Farm Streamlit application."""

from __future__ import annotations

import streamlit as st


def inject_app_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(250, 204, 21, 0.18), transparent 32%),
                radial-gradient(circle at top right, rgba(125, 211, 252, 0.18), transparent 28%),
                linear-gradient(180deg, #fffdf4 0%, #f5f8fc 56%, #eef5f8 100%);
        }
        .block-container {
            padding-top: 1.3rem;
            padding-bottom: 3rem;
            max-width: 1460px;
        }
        .designer-hero {
            margin-bottom: 1.2rem;
            padding: 1.8rem 1.9rem;
            border-radius: 28px;
            border: 1px solid rgba(202, 138, 4, 0.14);
            background:
                linear-gradient(135deg, rgba(255, 251, 214, 0.96), rgba(255, 255, 255, 0.94)),
                linear-gradient(135deg, rgba(202, 138, 4, 0.05), rgba(8, 145, 178, 0.06));
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
        }
        .designer-kicker {
            margin: 0 0 0.45rem 0;
            font-size: 0.78rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #a16207;
            font-weight: 700;
        }
        .designer-title {
            margin: 0;
            font-size: clamp(2rem, 2.8vw, 3.15rem);
            line-height: 1.02;
            color: #0f172a;
            font-weight: 800;
        }
        .designer-copy {
            max-width: 56rem;
            margin: 0.7rem 0 0 0;
            color: #475569;
            font-size: 1rem;
            line-height: 1.6;
        }
        .designer-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }
        .designer-badge {
            padding: 0.42rem 0.78rem;
            border-radius: 999px;
            border: 1px solid rgba(15, 23, 42, 0.08);
            background: rgba(255, 255, 255, 0.92);
            color: #0f766e;
            font-size: 0.82rem;
            font-weight: 700;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.55rem;
            margin-bottom: 1rem;
        }
        div[data-baseweb="tab-list"] button {
            min-height: 3rem;
            border-radius: 999px;
            border: 1px solid rgba(15, 23, 42, 0.08);
            background: rgba(255, 255, 255, 0.72);
            color: #475569;
            padding: 0.25rem 1rem;
        }
        div[data-baseweb="tab-list"] button[aria-selected="true"] {
            background: linear-gradient(135deg, #ca8a04, #0891b2);
            color: white;
            border-color: transparent;
            box-shadow: 0 12px 24px rgba(8, 145, 178, 0.16);
        }
        div[data-testid="stMetric"] {
            border-radius: 20px;
            border: 1px solid rgba(15, 23, 42, 0.08);
            background: rgba(255, 255, 255, 0.88);
            padding: 0.6rem 0.7rem;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_model_hero() -> None:
    badges = "".join(
        f'<span class="designer-badge">{label}</span>'
        for label in (
            "Investor workbook",
            "Project finance model",
            "Energy and cost analytics",
            "AI benchmark support",
        )
    )
    st.markdown(
        f"""
        <section class="designer-hero">
            <p class="designer-kicker">Infrastructure finance planning</p>
            <h1 class="designer-title">Solar Farm Financial Model</h1>
            <p class="designer-copy">
                Bring revenue, operating cost, debt, and return analytics into a cleaner executive shell
                with a presentation-ready workbook designed for sponsors, lenders, and investment committees.
            </p>
            <div class="designer-badges">{badges}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
