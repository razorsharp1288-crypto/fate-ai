from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHeaderView, QTableWidget, QTableWidgetItem

from ..components.widgets import Banner, BarChart, Card, Page, StatTile


class UsagePage(Page):
    def __init__(self, ctx):
        super().__init__("Usage Dashboard", "Requests, tokens, latency and estimated cost — recorded locally.")
        self.ctx = ctx
        self.body.addWidget(Banner(
            "Costs are <b>estimates</b> from the editable pricing table (pricing.json in your data folder, as of "
            f"{ctx.pricing.data.get('as_of', '?')}). Your provider's billing dashboard is the only authoritative total. "
            "Token counts marked ≈ were estimated because the provider did not report usage."))
        g = QGridLayout()
        self.tiles = {k: StatTile(lbl) for k, lbl in (
            ("conv", "Conversations"), ("req", "Requests"), ("tok", "Tokens"), ("cost", "Est. API cost"),
            ("lat", "Avg latency"), ("fail", "Failed requests"), ("local", "Local requests"), ("cloud", "Cloud requests"))}
        for i, t in enumerate(self.tiles.values()):
            g.addWidget(t, i // 4, i % 4)
        self.body.addLayout(g)
        chart = Card("Requests per day (last 30 days)")
        self.chart = BarChart()
        chart.add(self.chart)
        self.body.addWidget(chart)
        tc = Card("By provider and model")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Provider", "Model", "Type", "Requests", "Input tokens",
                                              "Output tokens", "Avg latency", "Est. cost"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(260)
        tc.add(self.table)
        self.body.addWidget(tc)

    def on_show(self):
        s = self.ctx.usage.summary()
        rows = self.ctx.usage.by_model()
        total_cost, unknown = 0.0, 0
        self.table.setRowCount(0)
        kinds = {p["id"]: p["kind"] for p in self.ctx.providers.configs()}
        for r_ in rows:
            cost = None if r_["is_local"] else self.ctx.pricing.estimate(kinds.get(r_["provider"], r_["provider"]),
                                                                          r_["model"], r_["input_tokens"] or 0,
                                                                          r_["output_tokens"] or 0)
            if cost is not None:
                total_cost += cost
            elif not r_["is_local"]:
                unknown += 1
            approx = "" if r_["exact"] else "≈"
            vals = [r_["provider"], r_["model"], "Local" if r_["is_local"] else "Cloud", r_["requests"],
                    f"{approx}{r_['input_tokens'] or 0:,}", f"{approx}{r_['output_tokens'] or 0:,}",
                    f"{(r_['avg_latency'] or 0) / 1000:.2f}s",
                    "free (local)" if r_["is_local"] else (f"≈ ${cost:.4f}" if cost is not None else "no price set")]
            row = self.table.rowCount()
            self.table.insertRow(row)
            for c, v in enumerate(vals):
                self.table.setItem(row, c, QTableWidgetItem(str(v)))
        req = s["requests"] or 0
        self.tiles["conv"].set(str(s["conversations"]))
        self.tiles["req"].set(str(req))
        self.tiles["tok"].set(f"{(s['input_tokens'] + s['output_tokens']):,}", "input + output")
        self.tiles["cost"].set(f"≈ ${total_cost:.2f}", f"{unknown} model(s) without pricing" if unknown else "estimate")
        self.tiles["lat"].set(f"{(s['avg_latency'] or 0) / 1000:.2f}s")
        self.tiles["fail"].set(str(s["failed"] or 0))
        self.tiles["local"].set(str(s["local_requests"] or 0))
        self.tiles["cloud"].set(str(req - (s["local_requests"] or 0)))
        self.chart.set_items([(d["day"][5:], d["requests"]) for d in self.ctx.usage.daily(30)])
