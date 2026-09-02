package risk

import (
	"testing"

	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/models"
)

func TestValidateSignal_RejectsHold(t *testing.T) {
	cfg := &config.Config{
		Risk: config.RiskConfig{DailyLossLimitPct: 5.0, MaxOpenPositions: 3},
	}
	mgr := NewManager(cfg, 10000)

	_, err := mgr.ValidateSignal(
		models.Signal{Action: models.SignalHold},
		models.Account{Equity: 10000, FreeMargin: 9000, Leverage: 100},
		0,
		models.Quote{Bid: 1.0850, Ask: 1.0852},
	)
	if err == nil {
		t.Fatal("expected hold signal to be rejected")
	}
}

func TestValidateSignal_ApprovesWithSLTP(t *testing.T) {
	cfg := &config.Config{
		Trading: config.TradingConfig{DefaultSymbol: "EURUSD", LotSize: 0.01},
		Risk: config.RiskConfig{
			DailyLossLimitPct: 5.0,
			MaxOpenPositions:  3,
			ProfitTargetPct:   10.0,
			MaxLossPct:        2.0,
			MinMarginLevelPct: 100,
		},
	}
	mgr := NewManager(cfg, 10000)

	req, err := mgr.ValidateSignal(
		models.Signal{Symbol: "EURUSD", Action: models.SignalBuy, Confidence: 0.8},
		models.Account{Equity: 10000, FreeMargin: 9000, Leverage: 100, MarginLevel: 999},
		0,
		models.Quote{Bid: 1.0850, Ask: 1.0852},
	)
	if err != nil {
		t.Fatalf("expected approval, got: %v", err)
	}
	if req.StopLoss >= 1.0852 {
		t.Fatalf("SL should be below entry for buy, got %f", req.StopLoss)
	}
	if req.TakeProfit <= 1.0852 {
		t.Fatalf("TP should be above entry for buy, got %f", req.TakeProfit)
	}
}

func TestShouldAutoExit_StopLoss(t *testing.T) {
	cfg := &config.Config{
		Risk: config.RiskConfig{AutoExitLossPct: 5.0},
	}
	mgr := NewManager(cfg, 10000)

	pos := models.Position{
		Side:         models.SideBuy,
		EntryPrice:   1.0900,
		CurrentPrice: 1.0840,
		StopLoss:     1.0850,
		TakeProfit:   1.1000,
		Margin:       100,
		UnrealizedPL: -50,
	}

	should, reason := mgr.ShouldAutoExit(pos)
	if !should {
		t.Fatal("expected auto-exit on SL breach")
	}
	if reason != models.CloseReasonStopLoss {
		t.Fatalf("unexpected reason: %s", reason)
	}
}
