import {
  IonBadge, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonChip, IonNote,
} from '@ionic/react';
import { analyticsOutline } from 'ionicons/icons';
import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { FinanceReport, Stance } from '../api/types';
import { LineChart } from '../components/Chart';
import { Page } from '../components/Page';
import { AsyncStatus, Empty } from '../components/Status';
import { KeyValueList, currencyOf, fmtIst, money, num, pct } from '../components/Widgets';
import { PopularIndian, TickerSearch } from '../components/India';
import { QuoteHeader } from '../components/Live';
import type { Benchmark } from '../api/types';
import { FLAVOR } from '../flavor';
import { useAsync } from '../hooks';
import type { FeatureModule } from './types';

const STANCE_COLOR: Record<Stance, string> = { bullish: 'success', neutral: 'medium', bearish: 'danger' };
const stanceColor = (s: string | null | undefined) => (s && s in STANCE_COLOR ? STANCE_COLOR[s as Stance] : 'medium');
const SENT_COLOR: Record<string, string> = { positive: 'success', negative: 'danger', neutral: 'medium' };

const Bullets: React.FC<{ title: string; items: string[]; color: string }> = ({ title, items, color }) =>
  items.length ? (
    <IonCard>
      <IonCardHeader><IonCardSubtitle color={color}>{title}</IonCardSubtitle></IonCardHeader>
      <IonCardContent><ul className="tight">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></IonCardContent>
    </IonCard>
  ) : null;

const PERIOD_ORDER = ['1w', '1m', '3m', '6m', 'ytd', '1y', '3y', '5y'];
const signed = (x: number | null | undefined) => (x === null || x === undefined ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
type BRow = [period: string, stock: number | null, index: number | null];
/** API.md section 9: flat stock_return_<p> / index_return_<p> fields. Falls back to the older { returns: { p: {stock, index} } } shape. */
function benchmarkRows(b: Benchmark): BRow[] {
  const rows: BRow[] = [];
  for (const p of PERIOD_ORDER) {
    const st = b[`stock_return_${p}`], ix = b[`index_return_${p}`];
    if (typeof st === 'number' || typeof ix === 'number') rows.push([p, typeof st === 'number' ? st : null, typeof ix === 'number' ? ix : null]);
  }
  if (rows.length) return rows;
  return Object.entries(b.returns ?? {})
    .filter(([, v]) => v && typeof v === 'object')
    .sort(([a], [c]) => (PERIOD_ORDER.indexOf(a) + 99) % 99 - (PERIOD_ORDER.indexOf(c) + 99) % 99)
    .map(([k, v]) => [k, v?.stock ?? null, v?.index ?? v?.benchmark ?? null]);
}
const BenchmarkCard: React.FC<{ b: Benchmark; ticker: string }> = ({ b, ticker }) => {
  const rows = benchmarkRows(b);
  const has = (x: unknown): x is number => typeof x === 'number';
  if (!rows.length && !has(b.beta) && !has(b.relative_strength_1y)) return null;
  const name = b.name ?? (b.symbol === '^GSPC' ? 'S&P 500' : 'NIFTY 50');
  const rs = b.relative_strength_1y;
  return (
    <IonCard>
      <IonCardHeader><IonCardSubtitle>vs {name}</IonCardSubtitle></IonCardHeader>
      <IonCardContent>
        {rows.length > 0 && (
          <table className="metric-table bench-table">
            <thead><tr><th>Period</th><th>{ticker.replace(/\.(NS|BO)$/, '')}</th><th>{name}</th><th>Diff</th></tr></thead>
            <tbody>
              {rows.map(([k, st, ix]) => {
                const diff = st !== null && ix !== null ? st - ix : null;
                return (
                  <tr key={k}>
                    <td>{k.toUpperCase()}</td><td>{signed(st)}</td><td>{signed(ix)}</td>
                    <td style={{ color: diff === null ? undefined : diff >= 0 ? 'var(--ion-color-success)' : 'var(--ion-color-danger)' }}>{signed(diff)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {has(b.beta) && <p className="small">Beta vs {name}: <strong>{num(b.beta, 2)}</strong> (1 = moves with the index)</p>}
        {has(rs) && <p className="small">Relative strength (1y): <strong style={{ color: rs >= 0 ? 'var(--ion-color-success)' : 'var(--ion-color-danger)' }}>{signed(rs)}</strong> vs {name}</p>}
      </IonCardContent>
    </IonCard>
  );
};

const ReportView: React.FC<{ r: FinanceReport }> = ({ r }) => {
  const chart = useMemo(() => ({
    labels: r.chart.map((p) => p.date),
    series: [
      { label: 'Close', data: r.chart.map((p) => p.close), color: '#2563eb', width: 2 },
      { label: 'SMA20', data: r.chart.map((p) => p.sma20), color: '#f59e0b', width: 1.2 },
      { label: 'SMA50', data: r.chart.map((p) => p.sma50), color: '#10b981', width: 1.2 },
      { label: 'SMA200', data: r.chart.map((p) => p.sma200), color: '#ef4444', width: 1.2 },
    ],
  }), [r]);
  const ind = r.indicators;
  const sym = r.normalized_ticker ?? r.ticker;
  const cur = currencyOf(sym, r.currency);
  return (
    <>
      <IonCard>
        <IonCardHeader>
          <IonCardSubtitle>{sym}{r.last_date ? ` · ${r.last_date}` : ''}{r.as_of_ist ? ` · as of ${fmtIst(r.as_of_ist)}` : ''}</IonCardSubtitle>
          <IonCardTitle>{r.company ?? sym}</IonCardTitle>
          <div className="chip-row">
            <IonBadge className="risk-badge" color={stanceColor(r.outlook)}>{(r.outlook ?? 'n/a').toUpperCase()}</IonBadge>
            {r.confidence && <IonChip outline>confidence: {r.confidence}</IonChip>}
            <IonChip color={r.mode === 'llm' ? 'tertiary' : 'medium'}>{r.mode_label || r.mode}</IonChip>
          </div>
        </IonCardHeader>
        <IonCardContent>
          {(r.display?.last_close || r.last_close !== null) && <div className="big-number">{r.display?.last_close ?? money(r.last_close, cur)}</div>}
          {(r.sector || r.industry || r.market_cap_display) && (
            <div className="chip-row">
              {r.sector && <IonChip outline>{r.sector}</IonChip>}
              {r.industry && <IonChip outline>{r.industry}</IonChip>}
              {r.market_cap_display && <IonChip outline>Mkt cap {r.market_cap_display}</IonChip>}
            </div>
          )}
          {r.summary && <p>{r.summary}</p>}
          {r.overall && <p><strong>Overall:</strong> {r.overall}</p>}
        </IonCardContent>
      </IonCard>

      {r.chart.length > 0 && (
        <IonCard>
          <IonCardHeader><IonCardSubtitle>Price with moving averages (~1 year)</IonCardSubtitle></IonCardHeader>
          <IonCardContent><LineChart labels={chart.labels} series={chart.series} height={250} /></IonCardContent>
        </IonCard>
      )}

      {r.benchmark && <BenchmarkCard b={r.benchmark} ticker={sym} />}

      <IonCard>
        <IonCardHeader><IonCardSubtitle>Indicators</IonCardSubtitle></IonCardHeader>
        <IonCardContent>
          <KeyValueList rows={[
            ['RSI (14)', num(ind.rsi, 1)], ['Volatility (1y)', pct(ind.volatility_1y)], ['Return (1m)', pct(ind.return_1m)], ['Max drawdown (1y)', pct(ind.max_drawdown_1y)],
          ]} />
        </IonCardContent>
      </IonCard>

      {r.agents.map((a) => (
        <IonCard key={a.name}>
          <IonCardHeader>
            <div className="agent-head">
              <IonCardTitle style={{ fontSize: '1.05rem' }}>{a.name}</IonCardTitle>
              {a.stance && <IonBadge color={stanceColor(a.stance)}>{a.stance}</IonBadge>}
            </div>
          </IonCardHeader>
          <IonCardContent>
            {a.summary && <p>{a.summary}</p>}
            {a.points.length > 0 && <ul className="tight">{a.points.map((p, i) => <li key={i}>{p}</li>)}</ul>}
          </IonCardContent>
        </IonCard>
      ))}

      <Bullets title="Bullish points" items={r.bullish} color="success" />
      <Bullets title="Bearish points" items={r.bearish} color="danger" />
      <Bullets title="Risks" items={r.risks} color="warning" />

      {r.headlines.length > 0 && (
        <IonCard>
          <IonCardHeader><IonCardSubtitle>Headlines</IonCardSubtitle></IonCardHeader>
          <IonCardContent>
            {r.headlines.map((h, i) => (
              <div key={i} className="headline">
                {h.link ? <a href={h.link} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
                <div className="row-center">
                  {h.publisher && <IonNote className="small">{h.publisher}</IonNote>}
                  {h.sentiment && <IonBadge color={SENT_COLOR[h.sentiment] ?? 'medium'}>{h.sentiment}</IonBadge>}
                </div>
              </div>
            ))}
          </IonCardContent>
        </IonCard>
      )}
    </>
  );
};

const InsightPage: React.FC = () => {
  const [text, setText] = useState('RELIANCE.NS');
  const [rk, setRk] = useState(0);
  const rep = useAsync<FinanceReport>();
  const go = (t = text) => { const T = t.trim(); if (T) { setText(T); rep.run(() => api.finance.report(T)); } };
  useEffect(() => { go('RELIANCE.NS'); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Page title={FLAVOR.appName} onRefresh={async () => { setRk((k) => k + 1); await rep.run(() => api.finance.report(rep.data?.ticker ?? text)); }}>
      <QuoteHeader ticker={rep.data?.ticker ?? text} refreshKey={rk} />
      <IonCard>
        <IonCardContent>
          <TickerSearch onPick={(t) => go(t)} busy={rep.loading} />
          <PopularIndian selected={rep.data?.ticker ?? text} onPick={(t) => go(t)} />
        </IonCardContent>
      </IonCard>
      <AsyncStatus loading={rep.loading} slow={rep.slow} error={rep.error} onRetry={() => go()} loadingLabel="Agents are analysing…"
        slowLabel="Fetching prices and news and running the agents. The server may also be waking up; this can take a minute." />
      {!rep.loading && !rep.error && !rep.data && <Empty>Search a ticker to get a multi-agent market report.</Empty>}
      {rep.data && !rep.loading && <ReportView r={rep.data} />}
      <p className="disclaimer">Not financial advice. Automated analysis for education only; do your own research.</p>
    </Page>
  );
};

const mod: FeatureModule = { tabs: [{ path: '/insight', label: 'Insight', icon: analyticsOutline, component: InsightPage }] };
export default mod;
