package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Mode     string         `yaml:"mode"`
	Server   ServerConfig   `yaml:"server"`
	Trading  TradingConfig  `yaml:"trading"`
	Risk     RiskConfig     `yaml:"risk"`
	Demo     DemoConfig     `yaml:"demo"`
	Broker   BrokerConfig   `yaml:"broker"`
	Monitor  MonitorConfig  `yaml:"monitor"`
	Logging  LoggingConfig  `yaml:"logging"`
	Control  ControlConfig  `yaml:"control"`
}

type ServerConfig struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
	// APIToken, when set, is required as a "Bearer <token>" Authorization header
	// on every endpoint except GET /health. Leave empty only for trusted local
	// dev use — the server logs a loud warning at startup if it's unset.
	APIToken string `yaml:"api_token"`
}

// ControlConfig configures the global trading enable/disable gate.
type ControlConfig struct {
	// StatePath is where the gate's enabled/disabled state is persisted so a
	// restart never silently re-enables trading. Relative paths resolve
	// against the process's working directory (repo root, by convention).
	StatePath string `yaml:"state_path"`
}

type TradingConfig struct {
	DefaultSymbol   string  `yaml:"default_symbol"`
	LotSize         float64 `yaml:"lot_size"`
	MaxSlippagePips float64 `yaml:"max_slippage_pips"`
}

type RiskConfig struct {
	ProfitTargetPct         float64 `yaml:"profit_target_pct"`
	MaxLossPct              float64 `yaml:"max_loss_pct"`
	DailyLossLimitPct       float64 `yaml:"daily_loss_limit_pct"`
	MaxOpenPositions        int     `yaml:"max_open_positions"`
	AutoExitLossPct         float64 `yaml:"auto_exit_loss_pct"`
	MinMarginLevelPct       float64 `yaml:"min_margin_level_pct"`
	EmergencyMarginLevelPct float64 `yaml:"emergency_margin_level_pct"`
}

type DemoConfig struct {
	InitialBalance float64 `yaml:"initial_balance"`
	Leverage       int     `yaml:"leverage"`
	SpreadPips     float64 `yaml:"spread_pips"`
}

type BrokerConfig struct {
	MT5BridgeURL string `yaml:"mt5_bridge_url"`
	APIToken     string `yaml:"api_token"`
	AccountID    int    `yaml:"account_id"`
	DemoServer   string `yaml:"demo_server"`
	LiveServer   string `yaml:"live_server"`
}

type MonitorConfig struct {
	IntervalMs int `yaml:"interval_ms"`
}

type LoggingConfig struct {
	Level string `yaml:"level"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	cfg.applyDefaults()
	return &cfg, nil
}

func (c *Config) applyDefaults() {
	if c.Server.Host == "" {
		// Local-only by default — an unauthenticated or open-bind API can place
		// real orders. Set server.host explicitly (and server.api_token) to
		// expose it beyond localhost.
		c.Server.Host = "127.0.0.1"
	}
	if c.Server.Port == 0 {
		c.Server.Port = 8080
	}
	if c.Control.StatePath == "" {
		c.Control.StatePath = "data/trading_state.json"
	}
	if c.Mode == "" {
		c.Mode = "demo"
	}
	if c.Trading.DefaultSymbol == "" {
		c.Trading.DefaultSymbol = "EURUSD"
	}
	if c.Trading.LotSize == 0 {
		c.Trading.LotSize = 0.01
	}
	if c.Risk.ProfitTargetPct == 0 {
		c.Risk.ProfitTargetPct = 10.0
	}
	if c.Risk.MaxLossPct == 0 {
		c.Risk.MaxLossPct = 2.0
	}
	if c.Risk.DailyLossLimitPct == 0 {
		c.Risk.DailyLossLimitPct = 5.0
	}
	if c.Risk.MaxOpenPositions == 0 {
		c.Risk.MaxOpenPositions = 3
	}
	if c.Demo.InitialBalance == 0 {
		c.Demo.InitialBalance = 10000.0
	}
	if c.Demo.Leverage == 0 {
		c.Demo.Leverage = 100
	}
	if c.Monitor.IntervalMs == 0 {
		c.Monitor.IntervalMs = 500
	}
}

func (c *Config) IsDemo() bool {
	return c.Mode == "demo"
}

func (c *Config) Addr() string {
	return fmt.Sprintf("%s:%d", c.Server.Host, c.Server.Port)
}
