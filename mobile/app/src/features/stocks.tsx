import {
  IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonChip, IonIcon, IonItem, IonLabel,
  IonList, IonNote, IonProgressBar, IonRange,
} from '@ionic/react';
import { bulbOutline, globeOutline, listOutline, schoolOutline, trendingUpOutline } from 'ionicons/icons';
import React, { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../api/client';
import type { ForecastMetric, StockForecast, StockTickers } from '../api/types';
import { LineChart } from '../components/Chart';
import { Page } from '../components/Page';
import { AsyncStatus, Empty, ErrorCard } from '../components/Status';
import { currencyOf, fmtIst, money, num } from '../components/Widgets';
import { MarketStatusPill, PopularIndian, TickerSearch } from '../components/India';
import { IntradayCard, QuoteHeader, WatchlistCard, useSelectedTicker, useWatchlist } from '../components/Live';
import { useIonRouter } from '@ionic/react';
import { FLAVOR } from '../flavor';
import { useAsync, useLoad } from '../hooks';
import type { FeatureModule } from './types';

const C = { close: '#64748b', rnn: '#f97316', lstm: '#8b5cf6', actual: '#0ea5e9' };

const TrainProgress: React.FC = () => {
  const [t, setT] = useState(0);
  useEffect(() => { const i = setInterval(() => setT((x) => x + 1), 1000); return () => clearInterval(i); }, []);
  return (
    <IonCard>
      <IonCardContent>
        <strong>Training RNN and LSTM…</strong> {t}s
        <IonProgressBar value={Math.min(0.95, t / 70)} />
        <IonNote className="small">Downloads price history and fits two networks. Usually about a minute; longer if the server was asleep.</IonNote>
      </IonCardContent>
    </IonCard>
  );
};

const MetricsTable: React.FC<{ m: StockForecast['metrics'] }> = ({ m }) => {
  const rows: [string, ForecastMetric][] = [['Naive (tomorrow = today)', m.naive_baseline], ['RNN', m.rnn], ['LSTM', m.lstm]];
  const bestRmse = Math.min(...rows.map(([, r]) => r.rmse ?? Infinity));
  return (
    <table className="metric-table">
      <thead><tr><th>Model</th><th>RMSE</th><th>MAE</th><th>MAPE</th><th>Dir. acc</th></tr></thead>
      <tbody>
        {rows.map(([name, r]) => (
          <tr key={name} className={r.rmse === bestRmse ? 'best' : ''}>
            <td>{name}</td><td>{num(r.rmse, 3)}</td><td>{num(r.mae, 3)}</td>
            <td>{r.mape_pct === null ? '—' : `${num(r.mape_pct)}%`}</td>
            <td>{r.direction_acc_pct === null ? '—' : `${num(r.direction_acc_pct, 1)}%`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

const ForecastPage: React.FC = () => {
  const tickers = useLoad<StockTickers>(() => api.stocks.tickers());
  const [ticker, setTicker] = useSelectedTicker();
  const [rk, setRk] = useState(0);
  const wl = useWatchlist();
  const [days, setDays] = useState(10);
  const fc = useAsync<StockForecast>();
  const train = useAsync<StockForecast>();

  const load = (t: string, d: number) => { train.reset(); fc.run(() => api.stocks.forecast(t, d)); };
  useEffect(() => { if (ticker) load(ticker, days); }, [ticker]); // eslint-disable-line

  // Servers with the universal India model (API.md section 9) forecast any symbol, so a 404 there means
  // "no price data", not "not trained yet". Older servers: 404 = train this ticker first.
  const universalServer = tickers.data?.universal === true;
  const notTrained = fc.error instanceof ApiError && fc.error.status === 404 && !universalServer;
  const data = train.data ?? fc.data;
  const [trainNote, setTrainNote] = useState<string | null>(null);
  useEffect(() => setTrainNote(null), [ticker]);

  const doTrain = async () => {
    setTrainNote(null);
    const r = await train.run(() => api.stocks.train(ticker));
    if (r) {
      if (r.trained === false) setTrainNote('This (hosted) server does not train at runtime, so it shows the universal India model forecast instead.');
      tickers.reload(); train.reset(); fc.run(() => (days === 10 ? Promise.resolve(r) : api.stocks.forecast(ticker, days)));
    }
  };
  const isUniversal = data?.model === 'universal';
  const shown = data?.normalized_ticker ?? data?.ticker ?? ticker;
  const uInfo = data?.model_info ?? tickers.data?.universal_info ?? null;
  const universalLabel = `Universal India model (trained on ~${uInfo?.trained_on ?? 50} NSE stocks)`;

  const chart = useMemo(() => {
    if (!data) return null;
    const h = data.history, f = data.forecast;
    const labels = [...h.map((p) => p.date), ...f.map((p) => p.date)];
    const pad = (n: number) => new Array(n).fill(null);
    return {
      labels,
      series: [
        { label: 'Close', data: [...h.map((p) => p.close), ...pad(f.length)], color: C.close },
        { label: 'RNN forecast', data: [...pad(h.length - 1), data.last_close, ...f.map((p) => p.rnn)], color: C.rnn, dashed: true },
        { label: 'LSTM forecast', data: [...pad(h.length - 1), data.last_close, ...f.map((p) => p.lstm)], color: C.lstm, dashed: true },
      ],
    };
  }, [data]);

  const last = data?.forecast[data.forecast.length - 1];
  const cur = data ? currencyOf(data.ticker, data.currency) : 'INR';

  return (
    <Page title={FLAVOR.appName} onRefresh={async () => { setRk((k) => k + 1); tickers.reload(); await fc.run(() => api.stocks.forecast(ticker, days)); }}>
      <QuoteHeader ticker={ticker} refreshKey={rk} />
      <IntradayCard ticker={ticker} refreshKey={rk} />
      <IonCard>
        <IonCardContent>
          <TickerSearch onPick={(t) => (t === ticker ? load(t, days) : setTicker(t))} onAdd={wl.add} isAdded={wl.has} />
          {!wl.has(shown) && <IonButton size="small" fill="clear" onClick={() => wl.add(shown)}>＋ Add {shown} to watchlist</IonButton>}
          <IonNote className="small">{universalServer ? 'Own per-ticker models (every other NSE stock uses the universal model)' : 'Already trained on the server'}</IonNote>
          <div className="chip-row">
            {(tickers.data?.trained ?? []).map((t) => (
              <IonChip key={t} color={t === ticker ? 'primary' : undefined} outline={t !== ticker} onClick={() => setTicker(t)}><IonLabel>{t}</IonLabel></IonChip>
            ))}
            {tickers.loading && <IonNote>loading tickers…</IonNote>}
          </div>
          {tickers.error && <ErrorCard error={tickers.error} onRetry={tickers.reload} />}
          <IonList lines="full">
            <IonItem>
              <IonRange labelPlacement="stacked" label={`Forecast horizon: ${days} trading day${days > 1 ? 's' : ''}`} min={1} max={30} step={1} value={days} pin snaps={false}
                onIonInput={(e) => setDays(e.detail.value as number)} onIonChange={(e) => load(ticker, e.detail.value as number)} />
            </IonItem>
          </IonList>
        </IonCardContent>
      </IonCard>

      {train.loading && <TrainProgress />}
      {train.error && <ErrorCard error={train.error} />}
      {trainNote && <IonCard color="light"><IonCardContent className="small">{trainNote}</IonCardContent></IonCard>}
      {!train.loading && <AsyncStatus loading={fc.loading} slow={fc.slow} error={notTrained ? null : fc.error} onRetry={() => load(ticker, days)} loadingLabel={`Loading ${ticker}…`} />}
      {notTrained && !train.loading && (
        <IonCard>
          <IonCardContent>
            <Empty>{fc.error!.message}</Empty>
            <IonButton expand="block" onClick={doTrain}><IonIcon slot="start" icon={schoolOutline} />Train {ticker} (~1 min)</IonButton>
          </IonCardContent>
        </IonCard>
      )}

      {data && chart && !fc.loading && !notTrained && (
        <>
          <IonCard>
            <IonCardHeader>
              <IonCardSubtitle>{data.name ? `${data.name} · ` : ''}{shown} · last close {data.last_date}{data.as_of_ist ? ` · as of ${fmtIst(data.as_of_ist)}` : ''}</IonCardSubtitle>
              <IonCardTitle className="big-number">{data.display?.last_close ?? money(data.last_close, cur)}</IonCardTitle>
              {last && <IonNote>In {data.forecast.length} trading days: RNN {money(last.rnn, cur)} · LSTM {money(last.lstm, cur)}</IonNote>}
              {data.model && (
                <div className="chip-row">
                  <IonChip outline color={isUniversal ? 'tertiary' : 'primary'} title={uInfo?.note ?? undefined}>
                    <IonIcon icon={isUniversal ? globeOutline : schoolOutline} />
                    <IonLabel>{isUniversal ? universalLabel : `Model trained on ${shown}`}</IonLabel>
                  </IonChip>
                </div>
              )}
              {isUniversal && (
                <IonNote className="small">
                  One RNN and one LSTM trained on liquid NSE stocks pooled together{uInfo?.trained_until ? ` (training data up to ${uInfo.trained_until})` : ''}. It works for any stock with about 3 months of history, so no per-stock training is needed.
                </IonNote>
              )}
            </IonCardHeader>
            <IonCardContent><LineChart labels={chart.labels} series={chart.series} height={260} /></IonCardContent>
          </IonCard>

          <IonCard>
            <IonCardHeader><IonCardTitle>How good is it?</IonCardTitle><IonCardSubtitle>{isUniversal ? `One-day-ahead error: live back-test of the universal model on ${shown}'s last ~120 trading days` : 'One-day-ahead error on the test period'}</IonCardSubtitle></IonCardHeader>
            <IonCardContent>
              <MetricsTable m={data.metrics} />
              {data.test.dates.length > 0 && (
                <div className="ion-margin-top">
                  <LineChart labels={data.test.dates} height={200} series={[
                    { label: 'Actual', data: data.test.actual, color: C.actual, width: 2.5 },
                    { label: 'RNN', data: data.test.rnn, color: C.rnn, width: 1.5 },
                    { label: 'LSTM', data: data.test.lstm, color: C.lstm, width: 1.5 },
                  ]} />
                </div>
              )}
            </IonCardContent>
          </IonCard>

          <IonCard>
            <IonCardHeader><IonCardTitle><IonIcon icon={bulbOutline} /> Why it can't beat the naive guess</IonCardTitle></IonCardHeader>
            <IonCardContent>
              Daily prices behave almost like a random walk: tomorrow's best single guess is roughly today's close. The networks learn mostly
              that, plus noise, so their errors end up close to (often slightly worse than) the naive baseline, and direction accuracy hovers near
              50%. Forecasts several weeks out are a smoothed continuation of the recent trend, not a prediction of news. Use this as a
              learning demo, not a trading signal.
            </IonCardContent>
          </IonCard>
          {!isUniversal && (
            <IonButton expand="block" fill="outline" onClick={doTrain} disabled={train.loading}>
              <IonIcon slot="start" icon={schoolOutline} />Retrain {shown} (~1 min)
            </IonButton>
          )}
        </>
      )}
      <p className="disclaimer">Educational demo. Not financial advice.</p>
    </Page>
  );
};

const MarketsPage: React.FC = () => {
  const [ticker, setTicker] = useSelectedTicker();
  const wl = useWatchlist();
  const router = useIonRouter();
  const [rk, setRk] = useState(0);
  const open = (t: string) => { setTicker(t); router.push('/forecast', 'forward'); };
  return (
    <Page title={FLAVOR.appName} onRefresh={() => { setRk((k) => k + 1); return new Promise((r) => setTimeout(r, 800)); }}>
      <MarketStatusPill refreshKey={rk} />
      <IonCard>
        <IonCardContent>
          <TickerSearch onPick={open} onAdd={wl.add} isAdded={wl.has} />
        </IonCardContent>
      </IonCard>
      <WatchlistCard onOpen={open} refreshKey={rk} />
      <IonCard>
        <IonCardContent><PopularIndian selected={ticker} onPick={open} /></IonCardContent>
      </IonCard>
      <p className="disclaimer">Prices may be delayed. Educational demo, not financial advice.</p>
    </Page>
  );
};

const mod: FeatureModule = {
  tabs: [
    { path: '/markets', label: 'Markets', icon: listOutline, component: MarketsPage },
    { path: '/forecast', label: 'Forecast', icon: trendingUpOutline, component: ForecastPage },
  ],
};
export default mod;
