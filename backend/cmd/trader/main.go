package main

import (
	"context"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prashant-sriharsh/trade/internal/api"
	"github.com/prashant-sriharsh/trade/internal/broker"
	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/demo"
	"github.com/prashant-sriharsh/trade/internal/monitor"
	"github.com/prashant-sriharsh/trade/internal/risk"
	"github.com/prashant-sriharsh/trade/internal/trading"
)

func main() {
	configPath := flag.String("config", "../config/config.yaml", "path to config file")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	cfg, err := config.Load(*configPath)
	if err != nil {
		logger.Error("load config", "err", err)
		os.Exit(1)
	}

	var brokerClient broker.Client
	var demoEngine *demo.Engine

	if cfg.IsDemo() {
		demoEngine = demo.NewEngine(cfg)
		brokerClient = demoEngine
		logger.Info("starting in demo mode", "balance", cfg.Demo.InitialBalance)
	} else {
		brokerClient = broker.NewMT5Client(cfg.Broker.MT5BridgeURL, cfg.Broker.APIToken, cfg.Broker.AccountID)
		logger.Info("starting in live mode", "bridge", cfg.Broker.MT5BridgeURL)
	}

	browserHook := broker.NewBrowserAutomation("https://my.exness.com")

	initialBalance := cfg.Demo.InitialBalance
	if !cfg.IsDemo() {
		initialBalance = 0
	}

	riskMgr := risk.NewManager(cfg, initialBalance)
	if cfg.IsDemo() {
		// Fresh demo session — don't carry phantom sim losses from prior runs
		riskMgr.ResetDaily(initialBalance)
	}
	engine := trading.NewEngine(cfg, brokerClient, riskMgr)

	posMonitor := monitor.New(cfg, engine, demoEngine, logger)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	posMonitor.Start(ctx)

	apiServer := api.NewServer(cfg, engine, demoEngine, browserHook, logger)
	httpServer := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      apiServer.Handler(),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	go func() {
		logger.Info("HTTP server listening", "addr", cfg.Addr(), "mode", cfg.Mode)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("HTTP server", "err", err)
			os.Exit(1)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	logger.Info("shutting down")
	cancel()
	posMonitor.Stop()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	_ = httpServer.Shutdown(shutdownCtx)
}
