import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="FinanceIQ - Personal Stock Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    h1 {
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    h2 {
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

@st.cache_resource
def get_db_connection():
    """Create database connection"""
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    db_name = os.getenv("DB_NAME", "financialnewsplatform")

    connection_string = f"postgresql://{user}:{password}@{host}/{db_name}"
    engine = create_engine(connection_string)
    return engine

# ============================================================================
# SCORING SYSTEM (CUSTOMIZABLE)
# ============================================================================

def compute_v2_score(quality, value, trajectory, weights=None):
    """
    Compute V2 score with customizable weights

    Default weights (you can adjust these):
    - Quality: 0.40 (profitability, margins, ROE)
    - Value: 0.35 (P/E, P/B, FCF multiples)
    - Trajectory: 0.25 (growth trends, momentum)
    """
    if weights is None:
        weights = {"quality": 0.40, "value": 0.35, "trajectory": 0.25}

    # Normalize weights
    total = sum(weights.values())
    weights = {k: v/total for k, v in weights.items()}

    # Geometric mean with weighted components
    if quality <= 0 or value <= 0 or trajectory <= 0:
        return 0

    weighted_product = (quality ** weights["quality"]) * \
                       (value ** weights["value"]) * \
                       (trajectory ** weights["trajectory"])

    return min(weighted_product, 1.0)  # Cap at 1.0

# ============================================================================
# PAGE: DASHBOARD
# ============================================================================

def page_dashboard():
    """Dashboard with quick stats and overview"""
    st.title("📊 FinanceIQ - Personal Stock Research")
    st.markdown("Refine your investment strategy with data-driven insights")

    try:
        engine = get_db_connection()

        # Get quick stats
        with engine.connect() as conn:
            # Total stocks tracked
            result = conn.execute(text("SELECT COUNT(*) as count FROM fundamentals"))
            total_stocks = result.fetchone()[0]

            # Average V2 score
            result = conn.execute(text("""
                SELECT AVG(
                    CASE
                        WHEN quality_score > 0 AND value_score > 0 AND trajectory_score > 0
                        THEN POWER(quality_score * value_score * trajectory_score, 1.0/3.0)
                        ELSE 0
                    END
                ) as avg_score
                FROM daily_scores
                WHERE date = CURRENT_DATE
            """))
            avg_score = result.fetchone()[0] or 0

            # Top performer today
            result = conn.execute(text("""
                SELECT symbol,
                    POWER(quality_score * value_score * trajectory_score, 1.0/3.0) as v2_score
                FROM daily_scores
                WHERE date = CURRENT_DATE
                ORDER BY v2_score DESC
                LIMIT 1
            """))
            top_stock = result.fetchone()

        # Display metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Stocks",
                f"{total_stocks:,}",
                "In database"
            )

        with col2:
            st.metric(
                "Avg V2 Score",
                f"{avg_score:.3f}",
                "Today"
            )

        with col3:
            if top_stock:
                st.metric(
                    "Top Stock",
                    top_stock[0],
                    f"V2: {top_stock[1]:.3f}"
                )
            else:
                st.metric("Top Stock", "—", "No data")

        with col4:
            st.metric(
                "Last Updated",
                datetime.now().strftime("%b %d, %H:%M"),
                "Today"
            )

        st.divider()

        # Quick info
        st.subheader("🎯 How to Use FinanceIQ")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.write("""
            **📊 Screener**
            Find stocks that match your criteria:
            - Filter by V2 score
            - Sector & industry
            - P/E ratio
            - Growth metrics
            """)

        with col2:
            st.write("""
            **⚙️ Customize Scoring**
            Adjust V2 weights to match your style:
            - Quality (profitability)
            - Value (valuation)
            - Trajectory (growth)
            """)

        with col3:
            st.write("""
            **👁️ Watchlist**
            Track stocks you're interested in:
            - Save custom lists
            - Monitor changes
            - Set alerts
            """)

    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        st.info("Make sure PostgreSQL is running and .env is configured correctly")

# ============================================================================
# PAGE: STOCK SCREENER
# ============================================================================

def page_screener():
    """Interactive stock screener"""
    st.title("🔍 Stock Screener")

    # Sidebar filters
    st.sidebar.header("Filters")

    min_v2_score = st.sidebar.slider(
        "Minimum V2 Score",
        0.0, 1.0, 0.70,
        help="Higher = better quality opportunities"
    )

    min_quality = st.sidebar.slider(
        "Minimum Quality Score",
        0.0, 1.0, 0.50,
        help="Profitability & efficiency"
    )

    min_value = st.sidebar.slider(
        "Minimum Value Score",
        0.0, 1.0, 0.50,
        help="Valuation metrics"
    )

    min_trajectory = st.sidebar.slider(
        "Minimum Trajectory Score",
        0.0, 1.0, 0.40,
        help="Growth & momentum"
    )

    max_pe = st.sidebar.number_input(
        "Maximum P/E Ratio",
        min_value=0, max_value=500, value=50,
        help="Leave at 500 for no limit"
    )

    sector = st.sidebar.text_input(
        "Sector (optional)",
        placeholder="e.g., Technology, Healthcare"
    )

    limit = st.sidebar.slider(
        "Results to Show",
        10, 500, 50
    )

    try:
        engine = get_db_connection()

        # Build query
        query = """
        SELECT
            f.symbol,
            f.sector,
            f.industry,
            f.pe_trailing as pe_ratio,
            f.market_cap,
            f.revenue_growth_yoy as revenue_growth,
            ds.quality_score,
            ds.value_score,
            ds.trajectory_score,
            POWER(ds.quality_score * ds.value_score * ds.trajectory_score, 1.0/3.0) as v2_score,
            ds.date
        FROM fundamentals f
        LEFT JOIN daily_scores ds ON f.symbol = ds.symbol AND ds.date = CURRENT_DATE
        WHERE 1=1
        """

        params = {}

        if min_v2_score > 0:
            query += " AND POWER(ds.quality_score * ds.value_score * ds.trajectory_score, 1.0/3.0) >= :min_v2"
            params["min_v2"] = min_v2_score

        if min_quality > 0:
            query += " AND ds.quality_score >= :min_qual"
            params["min_qual"] = min_quality

        if min_value > 0:
            query += " AND ds.value_score >= :min_val"
            params["min_val"] = min_value

        if min_trajectory > 0:
            query += " AND ds.trajectory_score >= :min_traj"
            params["min_traj"] = min_trajectory

        if max_pe < 500:
            query += " AND f.pe_trailing <= :max_pe"
            params["max_pe"] = max_pe

        if sector:
            query += " AND f.sector ILIKE :sector"
            params["sector"] = f"%{sector}%"

        query += " ORDER BY v2_score DESC NULLS LAST LIMIT :limit"
        params["limit"] = limit

        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()

        if rows:
            df = pd.DataFrame(rows, columns=columns)

            # Display stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Results Found", len(df))
            with col2:
                avg_v2 = df['v2_score'].mean()
                st.metric("Avg V2 Score", f"{avg_v2:.3f}")
            with col3:
                high_quality = len(df[df['v2_score'] >= 0.75])
                st.metric("High Quality (>0.75)", high_quality)

            st.divider()

            # Display table with visualization
            st.subheader("Results")

            # Create display dataframe
            display_df = df.copy()
            display_df = display_df.round({
                'quality_score': 3,
                'value_score': 3,
                'trajectory_score': 3,
                'v2_score': 3,
                'pe_ratio': 1,
                'revenue_growth': 4
            })

            # Color code scores
            def color_score(val):
                if pd.isna(val):
                    return 'background-color: #f0f0f0'
                if val >= 0.8:
                    return 'background-color: #90EE90'
                elif val >= 0.6:
                    return 'background-color: #FFD700'
                elif val >= 0.4:
                    return 'background-color: #FFA500'
                else:
                    return 'background-color: #FFB6C6'

            styled_df = display_df.style.applymap(
                color_score,
                subset=['quality_score', 'value_score', 'trajectory_score', 'v2_score']
            )

            st.dataframe(styled_df, use_container_width=True)

            # Distribution visualization
            st.subheader("Score Distribution")
            col1, col2 = st.columns(2)

            with col1:
                fig = go.Figure()
                fig.add_trace(go.Histogram(
                    x=df['v2_score'].dropna(),
                    nbinsx=20,
                    name='V2 Score',
                    marker_color='#1f77b4'
                ))
                fig.update_layout(
                    title="V2 Score Distribution",
                    xaxis_title="V2 Score",
                    yaxis_title="Count",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                # Score comparison
                avg_scores = {
                    'Quality': df['quality_score'].mean(),
                    'Value': df['value_score'].mean(),
                    'Trajectory': df['trajectory_score'].mean()
                }

                fig = go.Figure(data=[
                    go.Bar(x=list(avg_scores.keys()), y=list(avg_scores.values()),
                           marker_color=['#1f77b4', '#ff7f0e', '#2ca02c'])
                ])
                fig.update_layout(
                    title="Average Component Scores",
                    yaxis_title="Score",
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No stocks match your criteria. Try adjusting the filters.")

    except Exception as e:
        st.error(f"Error: {str(e)}")

# ============================================================================
# PAGE: CUSTOMIZE SCORING
# ============================================================================

def page_customize():
    """Customize scoring weights"""
    st.title("⚙️ Customize Your Scoring System")

    st.markdown("""
    Adjust the weights of the V2 scoring algorithm to match your investment style.
    """)

    # Explain scoring
    st.subheader("What Each Component Measures")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write("""
        **Quality Score** (40% default)

        Measures profitability & efficiency:
        - ROE & ROIC
        - Margins (gross, operating, net)
        - Consistent earnings

        Higher = Better business
        """)

    with col2:
        st.write("""
        **Value Score** (35% default)

        Measures valuation metrics:
        - P/E ratio
        - P/B ratio
        - Price-to-FCF

        Higher = Better valuation
        """)

    with col3:
        st.write("""
        **Trajectory Score** (25% default)

        Measures growth & momentum:
        - Revenue growth YoY
        - Earnings acceleration
        - FCF trends

        Higher = Improving fundamentals
        """)

    st.divider()

    # Weight sliders
    st.subheader("Adjust Weights")

    col1, col2, col3 = st.columns(3)

    with col1:
        quality_weight = st.slider(
            "Quality Weight",
            0, 100, 40,
            help="Higher = prioritize profitability"
        )

    with col2:
        value_weight = st.slider(
            "Value Weight",
            0, 100, 35,
            help="Higher = prioritize cheap stocks"
        )

    with col3:
        trajectory_weight = st.slider(
            "Trajectory Weight",
            0, 100, 25,
            help="Higher = prioritize growth"
        )

    # Normalize and display
    total = quality_weight + value_weight + trajectory_weight

    if total == 0:
        st.warning("At least one weight must be > 0")
    else:
        q_pct = (quality_weight / total) * 100
        v_pct = (value_weight / total) * 100
        t_pct = (trajectory_weight / total) * 100

        st.success(f"""
        Your Custom Weights:
        - Quality: {q_pct:.1f}%
        - Value: {v_pct:.1f}%
        - Trajectory: {t_pct:.1f}%
        """)

        # Store in session state
        st.session_state.quality_weight = q_pct
        st.session_state.value_weight = v_pct
        st.session_state.trajectory_weight = t_pct

    # Example
    st.divider()
    st.subheader("Example")

    example_quality = 0.80
    example_value = 0.65
    example_trajectory = 0.75

    if total > 0:
        example_v2 = compute_v2_score(
            example_quality,
            example_value,
            example_trajectory,
            {
                "quality": quality_weight,
                "value": value_weight,
                "trajectory": trajectory_weight
            }
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Quality Score", f"{example_quality:.2f}")
        with col2:
            st.metric("Value Score", f"{example_value:.2f}")
        with col3:
            st.metric("Trajectory Score", f"{example_trajectory:.2f}")
        with col4:
            st.metric("Your V2 Score", f"{example_v2:.3f}")

# ============================================================================
# PAGE: WATCHLIST
# ============================================================================

def page_watchlist():
    """Manage your watchlist"""
    st.title("👁️ Your Watchlist")

    # Initialize session state
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []

    col1, col2 = st.columns([3, 1])

    with col1:
        new_stock = st.text_input(
            "Add stock symbol (e.g., AAPL)",
            placeholder="Enter symbol..."
        ).upper()

    with col2:
        if st.button("➕ Add to Watchlist"):
            if new_stock and new_stock not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_stock)
                st.success(f"Added {new_stock}")
            elif new_stock in st.session_state.watchlist:
                st.warning(f"{new_stock} already in watchlist")

    if st.session_state.watchlist:
        st.divider()
        st.subheader(f"Watching {len(st.session_state.watchlist)} stocks")

        try:
            engine = get_db_connection()

            # Display each stock
            for symbol in st.session_state.watchlist:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT f.symbol, f.sector, f.pe_trailing,
                               ds.quality_score, ds.value_score, ds.trajectory_score,
                               POWER(ds.quality_score * ds.value_score * ds.trajectory_score, 1.0/3.0) as v2_score
                        FROM fundamentals f
                        LEFT JOIN daily_scores ds ON f.symbol = ds.symbol AND ds.date = CURRENT_DATE
                        WHERE f.symbol = :symbol
                    """), {"symbol": symbol})

                    row = result.fetchone()

                    if row:
                        col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])

                        with col1:
                            st.write(f"**{row[0]}**")
                        with col2:
                            st.write(f"{row[1] or 'N/A'}")
                        with col3:
                            st.metric("V2 Score", f"{row[6]:.3f}", delta=None, label_visibility="hidden")
                        with col4:
                            st.write(f"P/E: {row[2]:.1f}" if row[2] else "P/E: N/A")
                        with col5:
                            if st.button("✕", key=f"remove_{symbol}"):
                                st.session_state.watchlist.remove(symbol)
                                st.rerun()
                    else:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.warning(f"{symbol} not found in database")
                        with col2:
                            if st.button("✕", key=f"remove_{symbol}"):
                                st.session_state.watchlist.remove(symbol)
                                st.rerun()

        except Exception as e:
            st.error(f"Error: {str(e)}")

    else:
        st.info("👈 Add stocks to your watchlist to track them!")

# ============================================================================
# MAIN APP
# ============================================================================

def main():
    """Main app"""

    # Sidebar navigation
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Screener", "Customize Scoring", "Watchlist"],
        icons=["📊", "🔍", "⚙️", "👁️"]
    )

    st.sidebar.divider()

    # Help
    with st.sidebar.expander("ℹ️ Help & Info"):
        st.write("""
        **FinanceIQ** helps you find hidden investment opportunities.

        - **Dashboard**: Quick overview
        - **Screener**: Filter stocks by criteria
        - **Customize**: Adjust scoring weights
        - **Watchlist**: Track stocks you like

        Make sure PostgreSQL is running and .env is configured.
        """)

    # Route pages
    if page == "Dashboard":
        page_dashboard()
    elif page == "Screener":
        page_screener()
    elif page == "Customize Scoring":
        page_customize()
    elif page == "Watchlist":
        page_watchlist()

if __name__ == "__main__":
    main()
