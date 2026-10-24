"""Streamlit dashboard: search, compare, chart price history, track targets.

Run with:  streamlit run app.py
All logic lives in the plain modules (search, matching, db, alerts); this
file only lays out widgets, so the CLI and the UI always agree.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
from alerts import check_alerts
from formatting import inr
from history import seed_history
from search import search_all

st.set_page_config(page_title="Price Compare", page_icon="🛒", layout="wide")

# Colour follows the store, never its rank, so a store keeps its colour everywhere.
STORE_COLORS = {"ShopKart": "#2a78d6", "MegaMart": "#eb6834", "QuickBuy": "#1baf7a",
                "DummyJSON": "#eda100", "FakeStoreAPI": "#e87ba4"}
SIMULATED = {"ShopKart", "MegaMart", "QuickBuy"}

conn = db.connect()


@st.cache_data(ttl=600, show_spinner=False)
def cached_search(query: str):
    return search_all(query)


def offers_frame(groups) -> pd.DataFrame:
    rows = []
    for gi, g in enumerate(groups):
        best = g.best
        for o in g.offers:
            rows.append({
                "group": gi, "product": g.title, "store": o.store, "title": o.title,
                "price": o.price_inr, "shipping": o.shipping_inr, "total": o.total_inr,
                "delivery_days": o.delivery_days, "rating": o.rating,
                "in_stock": o.in_stock, "best": o is best, "link": o.url,
                "type": "simulated" if o.store in SIMULATED else "demo API",
            })
    return pd.DataFrame(rows)


st.title("🛒 Price comparison")
st.caption("ShopKart, MegaMart and QuickBuy are **simulated** stores from a local catalog. "
           "DummyJSON and FakeStoreAPI are real public **demo** APIs (USD converted at a "
           "fixed Rs 83/$). No real retailer is scraped.")

tab_compare, tab_history, tab_tracked = st.tabs(["Compare", "Price history", "Tracked & alerts"])

with tab_compare:
    with st.form("search"):
        c1, c2 = st.columns([4, 1])
        query = c1.text_input("Search a product", value=st.session_state.get("query", ""),
                              placeholder="e.g. iphone, laptop, perfume")
        submitted = c2.form_submit_button("Search", width="stretch")
    if submitted and query.strip():
        st.session_state["query"] = query.strip()
        res = cached_search(query.strip())
        db.save_offers(conn, res.offers, query.strip())
        st.session_state["result"] = res

    res = st.session_state.get("result")
    if res is None:
        st.info("Search for a product to compare prices across 5 stores.")
    else:
        for store, err in res.errors.items():
            st.warning(f"{store} is unavailable right now and was skipped ({err}).")
        if not res.groups:
            st.error(f'No offers found for "{res.query}".')
        else:
            df = offers_frame(res.groups)
            f1, f2, f3, f4 = st.columns(4)
            sort_by = f1.selectbox("Sort offers by", ["Total cost", "Rating", "Delivery"])
            min_rating = f2.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
            max_days = f3.slider("Max delivery days", 1, 30, 30)
            stock_only = f4.checkbox("In stock only", value=False)
            multi_only = st.checkbox("Only products sold by 2+ stores", value=True)

            st.caption(f'{len(res.offers)} offers from {len(res.stores_ok)} stores, '
                       f'grouped into {len(res.groups)} products.')
            shown = 0
            for gi, g in enumerate(res.groups):
                if multi_only and len(g.stores) < 2:
                    continue
                sub = df[df.group == gi]
                sub = sub[(sub.rating.fillna(0) >= min_rating)
                          & (sub.delivery_days.fillna(0) <= max_days)]
                if stock_only:
                    sub = sub[sub.in_stock]
                if sub.empty:
                    continue
                key = {"Total cost": ("total", True), "Rating": ("rating", False),
                       "Delivery": ("delivery_days", True)}[sort_by]
                sub = sub.sort_values(key[0], ascending=key[1], na_position="last")
                shown += 1
                best = g.best
                with st.container(border=True):
                    st.subheader(g.title)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Best deal", inr(best.total_inr), best.store, delta_color="off")
                    m2.metric("Saves vs priciest", inr(g.savings), g.worst.store, delta_color="off")
                    m3.metric("Stores", len(g.stores))
                    st.dataframe(
                        sub[["store", "title", "price", "shipping", "total", "delivery_days",
                             "rating", "in_stock", "best", "type", "link"]],
                        hide_index=True, width="stretch",
                        column_config={
                            "price": st.column_config.NumberColumn("Price (Rs)", format="%.0f"),
                            "shipping": st.column_config.NumberColumn("Shipping (Rs)", format="%.0f"),
                            "total": st.column_config.NumberColumn("Total (Rs)", format="%.0f"),
                            "delivery_days": st.column_config.NumberColumn("Delivery (days)"),
                            "rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
                            "in_stock": st.column_config.CheckboxColumn("In stock"),
                            "best": st.column_config.CheckboxColumn("Best deal"),
                            "link": st.column_config.LinkColumn("Link", display_text="open"),
                        },
                    )
                    with st.popover("Track this product"):
                        target = st.number_input("Alert me when total is at or below (Rs)",
                                                 min_value=1.0, step=100.0, key=f"t{gi}",
                                                 value=float(round(best.total_inr * 0.95)))
                        if st.button("Start tracking", key=f"b{gi}"):
                            db.track(conn, g, res.query, target)
                            st.success(f"Tracking {g.title} at {inr(target)}")
                if shown >= 15:
                    break
            if shown == 0:
                st.info("No offers match the current filters.")

with tab_history:
    rows = conn.execute(
        "SELECT product_key, MIN(title) AS title, COUNT(DISTINCT substr(seen_at,1,10)) AS days "
        "FROM offers GROUP BY product_key ORDER BY title").fetchall()
    c1, c2 = st.columns([4, 1])
    if c2.button("Seed 30 days of history", width="stretch"):
        n = seed_history(30, conn)
        st.success(f"Seeded {n} simulated rows.")
        st.rerun()
    if not rows:
        c1.info("No history yet: run a search or seed history.")
    else:
        options = {f"{r['title']}  ({r['days']} day(s))": r["product_key"] for r in rows}
        current = st.session_state.get("result")
        default = 0
        if current and current.groups:
            keys = current.groups[0].keys
            default = next((i for i, k in enumerate(options.values()) if k in keys), 0)
        label = c1.selectbox("Product", list(options), index=default)
        key = options[label]
        # Pull in sibling titles of the same product (e.g. "iPhone X" + "Apple iPhone X").
        keys = [key]
        if current:
            for g in current.groups:
                if key in g.keys:
                    keys = g.keys
        hist = pd.DataFrame([dict(r) for r in db.history(conn, keys)])
        fig = go.Figure()
        for store in sorted(hist.store.unique()):
            s = hist[hist.store == store]
            fig.add_trace(go.Scatter(
                x=s.day, y=s.total_inr, name=store, mode="lines+markers",
                line=dict(width=2, color=STORE_COLORS.get(store)), marker=dict(size=8),
                hovertemplate="%{x}<br>" + store + ": Rs %{y:,.0f}<extra></extra>"))
        fig.update_layout(title="Cheapest total price per store per day", hovermode="x unified",
                          yaxis_title="Total (Rs)", xaxis_title=None, height=420,
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, width="stretch")
        low = hist.loc[hist.total_inr.idxmin()]
        st.caption(f"Lowest recorded: {inr(low.total_inr)} at {low.store} on {low.day}.")
        with st.expander("Table view"):
            st.dataframe(hist.pivot_table(index="day", columns="store", values="total_inr"),
                         width="stretch")

with tab_tracked:
    items = db.tracked(conn)
    if not items:
        st.info("Nothing tracked yet. Use “Track this product” on the Compare tab.")
    else:
        if st.button("Check alerts now"):
            with st.spinner("Re-fetching tracked products..."):
                for r in check_alerts(conn):
                    if r.hit:
                        st.success(f"🎯 {r.title}: {inr(r.best)} at {r.store} "
                                   f"(target {inr(r.target)})")
                    elif r.best is None:
                        st.warning(f"{r.title}: {r.note}")
                    else:
                        st.info(f"{r.title}: best {inr(r.best)} at {r.store}, "
                                f"target {inr(r.target)}")
            items = db.tracked(conn)
        tdf = pd.DataFrame([dict(r) for r in items])
        tdf["status"] = [("✅ target hit" if r["last_best"] is not None and
                          r["last_best"] <= r["target_price"] else "⏳ waiting")
                         if r["last_best"] is not None else "not checked yet" for r in items]
        st.dataframe(tdf[["title", "query", "target_price", "last_best", "last_store",
                          "last_checked", "status"]], hide_index=True, width="stretch")
        remove = st.selectbox("Stop tracking", ["—"] + [r["title"] for r in items])
        if remove != "—" and st.button("Remove"):
            db.untrack(conn, next(r["id"] for r in items if r["title"] == remove))
            st.rerun()
