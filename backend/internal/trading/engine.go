package trading

import (
	"context"
	"fmt"

	"github.com/prashant-sriharsh/trade/internal/broker"
	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/control"
	"github.com/prashant-sriharsh/trade/internal/forex"
	"github.com/prashant-sriharsh/trade/internal/models"
	"github.com/prashant-sriharsh/trade/internal/risk"
)

// Engine orchestrates order execution with risk checks across demo or live brokers.
type Engine struct {
	cfg     *config.Config
	broker  broker.Client
	risk    *risk.Manager
	control *control.Gate
}

func NewEngine(cfg *config.Config, b broker.Client, riskMgr *risk.Manager, controlGate *control.Gate) *Engine {
	return &Engine{cfg: cfg, broker: b, risk: riskMgr, control: controlGate}
}

func (e *Engine) Broker() broker.Client {
	return e.broker
}

func (e *Engine) Risk() *risk.Manager {
	return e.risk
}

func (e *Engine) Control() *control.Gate {
	return e.control
}

func (e *Engine) GetAccount(ctx context.Context) (models.Account, error) {
	return e.broker.GetAccount(ctx)
}

func (e *Engine) GetQuote(ctx context.Context, symbol string) (models.Quote, error) {
	if symbol == "" {
		symbol = e.cfg.Trading.DefaultSymbol
	}
	return e.broker.GetQuote(ctx, symbol)
}

func (e *Engine) ListPositions(ctx context.Context) ([]models.Position, error) {
	return e.broker.ListPositions(ctx)
}

func (e *Engine) ListOrders(ctx context.Context) ([]models.Order, error) {
	if o, ok := e.broker.(interface{ Orders() []models.Order }); ok {
		return o.Orders(), nil
	}
	return []models.Order{}, nil
}

func (e *Engine) PlaceOrder(ctx context.Context, req models.OrderRequest) (models.Order, error) {
	if e.control != nil && !e.control.IsEnabled() {
		return models.Order{}, fmt.Errorf("trading disabled: %s", e.control.Status().Reason)
	}

	account, err := e.GetAccount(ctx)
	if err != nil {
		return models.Order{}, err
	}

	positions, err := e.ListPositions(ctx)
	if err != nil {
		return models.Order{}, err
	}

	status := e.risk.Status(len(positions))
	if !status.TradingAllowed {
		return models.Order{}, fmt.Errorf("trading blocked: %s", status.Reason)
	}

	if req.Symbol == "" {
		req.Symbol = e.cfg.Trading.DefaultSymbol
	}
	if req.Volume <= 0 {
		req.Volume = e.cfg.Trading.LotSize
	}
	if req.Type == "" {
		req.Type = models.OrderTypeMarket
	}

	quote, err := e.GetQuote(ctx, req.Symbol)
	if err != nil {
		return models.Order{}, err
	}

	if req.StopLoss == 0 || req.TakeProfit == 0 {
		entry := quote.Ask
		if req.Side == models.SideSell {
			entry = quote.Bid
		}
		margin := forex.Margin(req.Symbol, req.Volume, entry, account.Leverage)
		targetProfit := margin * e.cfg.Risk.ProfitTargetPct / 100
		maxLoss := account.Equity * e.cfg.Risk.MaxLossPct / 100
		if req.TakeProfit == 0 {
			req.TakeProfit = forex.PriceForProfit(req.Symbol, string(req.Side), entry, req.Volume, targetProfit)
		}
		if req.StopLoss == 0 {
			req.StopLoss = forex.PriceForLoss(req.Symbol, string(req.Side), entry, req.Volume, maxLoss)
		}
	}

	if account.MarginLevel > 0 && account.MarginLevel < e.cfg.Risk.MinMarginLevelPct {
		return models.Order{}, fmt.Errorf("margin level %.1f%% below minimum %.1f%%",
			account.MarginLevel, e.cfg.Risk.MinMarginLevelPct)
	}

	order, err := e.broker.PlaceOrder(ctx, req)
	if err != nil {
		return order, err
	}
	return order, nil
}

func (e *Engine) ProcessSignal(ctx context.Context, signal models.Signal) (models.Order, error) {
	if e.control != nil && !e.control.IsEnabled() {
		return models.Order{}, fmt.Errorf("trading disabled: %s", e.control.Status().Reason)
	}

	account, err := e.GetAccount(ctx)
	if err != nil {
		return models.Order{}, err
	}

	positions, err := e.ListPositions(ctx)
	if err != nil {
		return models.Order{}, err
	}

	quote, err := e.GetQuote(ctx, signal.Symbol)
	if err != nil {
		return models.Order{}, err
	}

	req, err := e.risk.ValidateSignal(signal, account, len(positions), quote)
	if err != nil {
		return models.Order{}, err
	}

	order, err := e.broker.PlaceOrder(ctx, *req)
	if err != nil {
		return order, err
	}
	return order, nil
}

func (e *Engine) ClosePosition(ctx context.Context, positionID string, reason models.CloseReason) (models.ClosedTrade, error) {
	if d, ok := e.broker.(interface {
		ClosePositionWithReason(string, models.CloseReason) (models.ClosedTrade, error)
	}); ok && reason != models.CloseReasonManual {
		trade, err := d.ClosePositionWithReason(positionID, reason)
		if err != nil {
			return trade, err
		}
		e.risk.RecordClosedTrade(trade)
		return trade, nil
	}

	trade, err := e.broker.ClosePosition(ctx, positionID)
	if err != nil {
		return trade, err
	}
	trade.Reason = reason
	e.risk.RecordClosedTrade(trade)
	return trade, nil
}

// CloseAllPositions closes every open position with the given reason. It keeps
// going after an individual failure and returns whichever trades succeeded
// plus an error listing how many failed, so callers (emergency margin close,
// the stop-all control endpoint) get a best-effort sweep rather than an
// all-or-nothing operation.
func (e *Engine) CloseAllPositions(ctx context.Context, reason models.CloseReason) ([]models.ClosedTrade, error) {
	positions, err := e.ListPositions(ctx)
	if err != nil {
		return nil, err
	}

	closed := make([]models.ClosedTrade, 0, len(positions))
	failed := 0
	for _, pos := range positions {
		trade, err := e.ClosePosition(ctx, pos.ID, reason)
		if err != nil {
			failed++
			continue
		}
		closed = append(closed, trade)
	}
	if failed > 0 {
		return closed, fmt.Errorf("%d of %d positions failed to close", failed, len(positions))
	}
	return closed, nil
}

func (e *Engine) RiskStatus(ctx context.Context) (models.RiskStatus, error) {
	positions, err := e.ListPositions(ctx)
	if err != nil {
		return models.RiskStatus{}, err
	}
	return e.risk.Status(len(positions)), nil
}
