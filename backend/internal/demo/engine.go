package demo

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/forex"
	"github.com/prashant-sriharsh/trade/internal/models"
)

// Engine simulates broker fills for demo mode.
type Engine struct {
	cfg       *config.Config
	mu        sync.RWMutex
	balance   float64
	usedMargin float64
	positions map[string]*models.Position
	orders    []models.Order
	trades    []models.ClosedTrade
	// Simple synthetic price per symbol (mid price)
	prices map[string]float64
	// Live Exness quotes synced via browser bridge, keyed by symbol (disables
	// that symbol's random walk while fresh). Must stay per-symbol — a single
	// shared quote previously leaked one symbol's price onto every other
	// symbol's GetQuote/Tick.
	externalQuotes map[string]externalQuote
}

type externalQuote struct {
	bid    float64
	ask    float64
	syncAt time.Time
}

func NewEngine(cfg *config.Config) *Engine {
	initial := cfg.Demo.InitialBalance
	symbol := cfg.Trading.DefaultSymbol
	defaultPrice := 1.1000
	if forex.IsGold(symbol) {
		defaultPrice = 4308.0
	}
	return &Engine{
		cfg:            cfg,
		balance:        initial,
		positions:      make(map[string]*models.Position),
		prices:         map[string]float64{symbol: defaultPrice},
		externalQuotes: make(map[string]externalQuote),
	}
}

func (e *Engine) Name() string { return "demo-engine" }

func (e *Engine) GetAccount(ctx context.Context) (models.Account, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.accountSnapshot(), nil
}

func (e *Engine) accountSnapshot() models.Account {
	equity := e.balance
	margin := e.usedMargin
	for _, p := range e.positions {
		equity += p.UnrealizedPL
	}
	free := equity - margin
	level := 0.0
	if margin > 0 {
		level = equity / margin * 100
	}
	return models.Account{
		Balance:     e.balance,
		Equity:      equity,
		Margin:      margin,
		FreeMargin:  free,
		MarginLevel: level,
		Leverage:    e.cfg.Demo.Leverage,
		Currency:    "USD",
	}
}

func (e *Engine) GetQuote(ctx context.Context, symbol string) (models.Quote, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.getQuoteLocked(symbol), nil
}

// SyncQuote applies live Exness bid/ask and optional account balance from browser sync.
func (e *Engine) SyncQuote(symbol string, bid, ask, balance, equity float64) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if symbol == "" {
		symbol = e.cfg.Trading.DefaultSymbol
	}
	if bid > 0 && ask > 0 {
		e.prices[symbol] = (bid + ask) / 2
		e.externalQuotes[symbol] = externalQuote{bid: bid, ask: ask, syncAt: time.Now().UTC()}
	}
	if balance > 0 {
		e.balance = balance
	}
	_ = equity

	quote := e.getQuoteLocked(symbol)
	for _, p := range e.positions {
		if p.Symbol != symbol {
			continue
		}
		if p.Side == models.SideBuy {
			p.CurrentPrice = quote.Bid
		} else {
			p.CurrentPrice = quote.Ask
		}
		p.UnrealizedPL = forex.UnrealizedPL(p.Symbol, string(p.Side), p.EntryPrice, p.CurrentPrice, p.Volume)
	}
}

func (e *Engine) HasFreshExternalQuote(symbol string, maxAge time.Duration) bool {
	e.mu.RLock()
	defer e.mu.RUnlock()
	q, ok := e.externalQuotes[symbol]
	return ok && time.Since(q.syncAt) <= maxAge
}

func (e *Engine) PlaceOrder(ctx context.Context, req models.OrderRequest) (models.Order, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	quote := e.getQuoteLocked(req.Symbol)

	fill := quote.Ask
	if req.Side == models.SideSell {
		fill = quote.Bid
	}

	margin := forex.Margin(req.Symbol, req.Volume, fill, e.cfg.Demo.Leverage)
	acc := e.accountSnapshot()
	if margin > acc.FreeMargin {
		order := models.Order{
			ID:        uuid.New().String(),
			Request:   req,
			Status:    models.OrderStatusRejected,
			Message:   "insufficient margin",
			CreatedAt: time.Now().UTC(),
		}
		e.orders = append(e.orders, order)
		return order, fmt.Errorf("insufficient margin")
	}

	now := time.Now().UTC()
	posID := uuid.New().String()
	orderID := uuid.New().String()

	pos := &models.Position{
		ID:           posID,
		OrderID:      orderID,
		Symbol:       req.Symbol,
		Side:         req.Side,
		Volume:       req.Volume,
		EntryPrice:   fill,
		CurrentPrice: fill,
		StopLoss:     req.StopLoss,
		TakeProfit:   req.TakeProfit,
		Margin:       margin,
		OpenedAt:     now,
	}
	e.positions[posID] = pos
	e.usedMargin += margin

	order := models.Order{
		ID:        orderID,
		Request:   req,
		Status:    models.OrderStatusFilled,
		FillPrice: fill,
		CreatedAt: now,
		FilledAt:  &now,
	}
	e.orders = append(e.orders, order)
	return order, nil
}

func (e *Engine) ClosePosition(ctx context.Context, positionID string) (models.ClosedTrade, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	pos, ok := e.positions[positionID]
	if !ok {
		return models.ClosedTrade{}, fmt.Errorf("position not found: %s", positionID)
	}

	quote := e.getQuoteLocked(pos.Symbol)

	exit := quote.Bid
	if pos.Side == models.SideSell {
		exit = quote.Ask
	}

	pl := forex.UnrealizedPL(pos.Symbol, string(pos.Side), pos.EntryPrice, exit, pos.Volume)
	e.balance += pl
	e.usedMargin -= pos.Margin
	delete(e.positions, positionID)

	trade := models.ClosedTrade{
		Position:   *pos,
		ExitPrice:  exit,
		RealizedPL: pl,
		Reason:     models.CloseReasonManual,
		ClosedAt:   time.Now().UTC(),
	}
	e.trades = append(e.trades, trade)
	return trade, nil
}

func (e *Engine) ListPositions(ctx context.Context) ([]models.Position, error) {
	e.mu.RLock()
	defer e.mu.RUnlock()

	out := make([]models.Position, 0, len(e.positions))
	for _, p := range e.positions {
		out = append(out, *p)
	}
	return out, nil
}

// Tick updates synthetic prices and position P&L (called by monitor).
func (e *Engine) Tick(symbol string, deltaPips float64) {
	e.mu.Lock()
	defer e.mu.Unlock()

	if q, ok := e.externalQuotes[symbol]; ok && time.Since(q.syncAt) <= 30*time.Second {
		return
	}

	pip := forex.PipSize(symbol)
	mid, ok := e.prices[symbol]
	if !ok {
		mid = 1.1000
	}
	e.prices[symbol] = mid + deltaPips*pip

	quote := e.getQuoteLocked(symbol)
	for _, p := range e.positions {
		if p.Symbol != symbol {
			continue
		}
		if p.Side == models.SideBuy {
			p.CurrentPrice = quote.Bid
		} else {
			p.CurrentPrice = quote.Ask
		}
		p.UnrealizedPL = forex.UnrealizedPL(p.Symbol, string(p.Side), p.EntryPrice, p.CurrentPrice, p.Volume)
	}
}

func (e *Engine) ClosePositionWithReason(positionID string, reason models.CloseReason) (models.ClosedTrade, error) {
	trade, err := e.ClosePosition(context.Background(), positionID)
	if err != nil {
		return trade, err
	}
	trade.Reason = reason
	e.mu.Lock()
	if len(e.trades) > 0 {
		e.trades[len(e.trades)-1].Reason = reason
	}
	e.mu.Unlock()
	return trade, nil
}

func (e *Engine) Orders() []models.Order {
	e.mu.RLock()
	defer e.mu.RUnlock()
	out := make([]models.Order, len(e.orders))
	copy(out, e.orders)
	return out
}

func (e *Engine) Trades() []models.ClosedTrade {
	e.mu.RLock()
	defer e.mu.RUnlock()
	out := make([]models.ClosedTrade, len(e.trades))
	copy(out, e.trades)
	return out
}

func (e *Engine) getQuoteLocked(symbol string) models.Quote {
	mid, ok := e.prices[symbol]
	if !ok {
		mid = 1.1000
		e.prices[symbol] = mid
	}
	if q, ok := e.externalQuotes[symbol]; ok && time.Since(q.syncAt) <= 30*time.Second && q.bid > 0 && q.ask > 0 {
		return models.Quote{
			Symbol: symbol,
			Bid:    q.bid,
			Ask:    q.ask,
			Spread: q.ask - q.bid,
			Time:   q.syncAt,
		}
	}
	spread := forex.PipSize(symbol) * e.cfg.Demo.SpreadPips
	return models.Quote{
		Symbol: symbol,
		Bid:    mid - spread/2,
		Ask:    mid + spread/2,
		Spread: spread,
		Time:   time.Now().UTC(),
	}
}
