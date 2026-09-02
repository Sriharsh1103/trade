package risk

import (
	"fmt"
	"sync"

	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/forex"
	"github.com/prashant-sriharsh/trade/internal/models"
)

type Manager struct {
	cfg               *config.Config
	mu                sync.RWMutex
	dailyStartBalance float64
	dailyPL           float64
}

func NewManager(cfg *config.Config, initialBalance float64) *Manager {
	return &Manager{
		cfg:               cfg,
		dailyStartBalance: initialBalance,
	}
}

func (m *Manager) Status(openPositions int) models.RiskStatus {
	m.mu.RLock()
	defer m.mu.RUnlock()

	limit := m.dailyStartBalance * m.cfg.Risk.DailyLossLimitPct / 100
	allowed := true
	reason := ""

	if m.dailyPL <= -limit {
		allowed = false
		reason = "daily loss limit reached"
	}
	if openPositions >= m.cfg.Risk.MaxOpenPositions {
		allowed = false
		if reason != "" {
			reason += "; "
		}
		reason += "max open positions reached"
	}

	return models.RiskStatus{
		DailyStartBalance: m.dailyStartBalance,
		DailyPL:           m.dailyPL,
		DailyLossLimit:    limit,
		OpenPositions:     openPositions,
		MaxOpenPositions:  m.cfg.Risk.MaxOpenPositions,
		TradingAllowed:    allowed,
		Reason:            reason,
	}
}

func (m *Manager) ValidateSignal(signal models.Signal, account models.Account, openPositions int, quote models.Quote) (*models.OrderRequest, error) {
	if signal.Action == models.SignalHold {
		return nil, fmt.Errorf("hold signal — no order")
	}

	status := m.Status(openPositions)
	if !status.TradingAllowed {
		return nil, fmt.Errorf("trading blocked: %s", status.Reason)
	}

	if account.MarginLevel > 0 && account.MarginLevel < m.cfg.Risk.MinMarginLevelPct {
		return nil, fmt.Errorf("margin level %.1f%% below minimum %.1f%%", account.MarginLevel, m.cfg.Risk.MinMarginLevelPct)
	}

	symbol := signal.Symbol
	if symbol == "" {
		symbol = m.cfg.Trading.DefaultSymbol
	}

	side := models.SideBuy
	if signal.Action == models.SignalSell {
		side = models.SideSell
	}

	volume := m.cfg.Trading.LotSize
	entry := quote.Ask
	if side == models.SideSell {
		entry = quote.Bid
	}

	margin := forex.Margin(symbol, volume, entry, account.Leverage)
	if margin > account.FreeMargin {
		return nil, fmt.Errorf("insufficient free margin: need %.2f, have %.2f", margin, account.FreeMargin)
	}

	targetProfit := margin * m.cfg.Risk.ProfitTargetPct / 100
	maxLoss := account.Equity * m.cfg.Risk.MaxLossPct / 100

	tp := forex.PriceForProfit(symbol, string(side), entry, volume, targetProfit)
	sl := forex.PriceForLoss(symbol, string(side), entry, volume, maxLoss)

	return &models.OrderRequest{
		Symbol:     symbol,
		Side:       side,
		Type:       models.OrderTypeMarket,
		Volume:     volume,
		StopLoss:   sl,
		TakeProfit: tp,
	}, nil
}

func (m *Manager) ShouldAutoExit(pos models.Position) (bool, models.CloseReason) {
	plPct := 0.0
	if pos.Margin > 0 {
		plPct = pos.UnrealizedPL / pos.Margin * 100
	}

	if pos.TakeProfit > 0 {
		if pos.Side == models.SideBuy && pos.CurrentPrice >= pos.TakeProfit {
			return true, models.CloseReasonTakeProfit
		}
		if pos.Side == models.SideSell && pos.CurrentPrice <= pos.TakeProfit {
			return true, models.CloseReasonTakeProfit
		}
	}

	if pos.StopLoss > 0 {
		if pos.Side == models.SideBuy && pos.CurrentPrice <= pos.StopLoss {
			return true, models.CloseReasonStopLoss
		}
		if pos.Side == models.SideSell && pos.CurrentPrice >= pos.StopLoss {
			return true, models.CloseReasonStopLoss
		}
	}

	if plPct <= -m.cfg.Risk.AutoExitLossPct {
		return true, models.CloseReasonAutoExit
	}

	return false, ""
}

func (m *Manager) ShouldEmergencyClose(account models.Account) bool {
	return account.MarginLevel > 0 && account.MarginLevel < m.cfg.Risk.EmergencyMarginLevelPct
}

func (m *Manager) RecordClosedTrade(trade models.ClosedTrade) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.dailyPL += trade.RealizedPL
}

func (m *Manager) ResetDaily(balance float64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.dailyStartBalance = balance
	m.dailyPL = 0
}
