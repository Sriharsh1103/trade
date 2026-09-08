package monitor

import (
	"context"
	"log/slog"
	"math/rand"
	"sync"
	"time"

	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/demo"
	"github.com/prashant-sriharsh/trade/internal/models"
	"github.com/prashant-sriharsh/trade/internal/trading"
)

type Monitor struct {
	cfg     *config.Config
	engine  *trading.Engine
	demo    *demo.Engine
	logger  *slog.Logger
	stopCh  chan struct{}
	wg      sync.WaitGroup
}

func New(cfg *config.Config, engine *trading.Engine, demoEngine *demo.Engine, logger *slog.Logger) *Monitor {
	return &Monitor{
		cfg:    cfg,
		engine: engine,
		demo:   demoEngine,
		logger: logger,
		stopCh: make(chan struct{}),
	}
}

func (m *Monitor) Start(ctx context.Context) {
	m.wg.Add(1)
	go m.loop(ctx)
}

func (m *Monitor) Stop() {
	close(m.stopCh)
	m.wg.Wait()
}

func (m *Monitor) loop(ctx context.Context) {
	defer m.wg.Done()

	interval := time.Duration(m.cfg.Monitor.IntervalMs) * time.Millisecond
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	symbol := m.cfg.Trading.DefaultSymbol

	for {
		select {
		case <-ctx.Done():
			return
		case <-m.stopCh:
			return
		case <-ticker.C:
			m.tick(ctx, symbol)
		}
	}
}

func (m *Monitor) tick(ctx context.Context, symbol string) {
	if m.demo != nil {
		// Small random walk for demo price simulation
		delta := (rand.Float64() - 0.5) * 2
		m.demo.Tick(symbol, delta)
	}

	account, err := m.engine.GetAccount(ctx)
	if err != nil {
		m.logger.Warn("monitor: get account", "err", err)
		return
	}

	if m.engine.Risk().ShouldEmergencyClose(account) {
		m.logger.Error("emergency margin level — closing all positions",
			"margin_level", account.MarginLevel)
		m.closeAll(ctx, models.CloseReasonEmergency)
		return
	}

	positions, err := m.engine.ListPositions(ctx)
	if err != nil {
		m.logger.Warn("monitor: list positions", "err", err)
		return
	}

	for _, pos := range positions {
		shouldExit, reason := m.engine.Risk().ShouldAutoExit(pos)
		if shouldExit {
			m.logger.Info("auto-exit triggered",
				"position", pos.ID,
				"reason", reason,
				"unrealized_pl", pos.UnrealizedPL)
			if _, err := m.engine.ClosePosition(ctx, pos.ID, reason); err != nil {
				m.logger.Warn("monitor: close position", "id", pos.ID, "err", err)
			}
		}
	}
}

func (m *Monitor) closeAll(ctx context.Context, reason models.CloseReason) {
	if _, err := m.engine.CloseAllPositions(ctx, reason); err != nil {
		m.logger.Warn("monitor: emergency close", "err", err)
	}
}
