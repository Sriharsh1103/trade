package api

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/prashant-sriharsh/trade/internal/broker"
	"github.com/prashant-sriharsh/trade/internal/config"
	"github.com/prashant-sriharsh/trade/internal/demo"
	"github.com/prashant-sriharsh/trade/internal/models"
	"github.com/prashant-sriharsh/trade/internal/trading"
)

type Server struct {
	cfg       *config.Config
	engine    *trading.Engine
	demo      *demo.Engine
	browser   *broker.BrowserAutomation
	logger    *slog.Logger
	mux       *http.ServeMux
}

func NewServer(cfg *config.Config, engine *trading.Engine, demoEngine *demo.Engine, browser *broker.BrowserAutomation, logger *slog.Logger) *Server {
	s := &Server{
		cfg:     cfg,
		engine:  engine,
		demo:    demoEngine,
		browser: browser,
		logger:  logger,
		mux:     http.NewServeMux(),
	}
	s.routes()
	if s.cfg.Server.APIToken == "" {
		s.logger.Warn("server.api_token is not set — every endpoint except /health is unauthenticated; do not expose this port beyond localhost")
	}
	return s
}

func (s *Server) Handler() http.Handler {
	return s.withAuth(s.mux)
}

// withAuth requires "Authorization: Bearer <server.api_token>" on every route
// except the health check. If no token is configured, auth is skipped (local
// dev only — NewServer already logs a warning in that case).
func (s *Server) withAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.Server.APIToken == "" || r.URL.Path == "/health" {
			next.ServeHTTP(w, r)
			return
		}
		auth := r.Header.Get("Authorization")
		want := "Bearer " + s.cfg.Server.APIToken
		if auth == "" || auth != want {
			writeError(w, http.StatusUnauthorized, errors.New("missing or invalid bearer token"))
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /health", s.handleHealth)
	s.mux.HandleFunc("GET /api/v1/account", s.handleAccount)
	s.mux.HandleFunc("GET /api/v1/positions", s.handlePositions)
	s.mux.HandleFunc("GET /api/v1/orders", s.handleOrders)
	s.mux.HandleFunc("POST /api/v1/orders", s.handlePlaceOrder)
	s.mux.HandleFunc("DELETE /api/v1/positions/{id}", s.handleClosePosition)
	s.mux.HandleFunc("POST /api/v1/signals", s.handleSignal)
	s.mux.HandleFunc("GET /api/v1/risk/status", s.handleRiskStatus)
	s.mux.HandleFunc("POST /api/v1/risk/reset", s.handleRiskReset)
	s.mux.HandleFunc("GET /api/v1/quote/{symbol}", s.handleQuote)
	s.mux.HandleFunc("GET /api/v1/broker/status", s.handleBrokerStatus)
	s.mux.HandleFunc("POST /api/v1/broker/browser/enable", s.handleBrowserEnable)
	s.mux.HandleFunc("POST /api/v1/broker/browser/sync", s.handleBrowserSync)
	s.mux.HandleFunc("GET /api/v1/control/status", s.handleControlStatus)
	s.mux.HandleFunc("POST /api/v1/control/enable", s.handleControlEnable)
	s.mux.HandleFunc("POST /api/v1/control/disable", s.handleControlDisable)
	s.mux.HandleFunc("POST /api/v1/control/stop-all", s.handleControlStopAll)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status": "ok",
		"mode":   s.cfg.Mode,
	})
}

func (s *Server) handleAccount(w http.ResponseWriter, r *http.Request) {
	acc, err := s.engine.GetAccount(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, acc)
}

func (s *Server) handlePositions(w http.ResponseWriter, r *http.Request) {
	pos, err := s.engine.ListPositions(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, pos)
}

func (s *Server) handleOrders(w http.ResponseWriter, r *http.Request) {
	orders, err := s.engine.ListOrders(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, orders)
}

func (s *Server) handlePlaceOrder(w http.ResponseWriter, r *http.Request) {
	var req models.OrderRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}

	order, err := s.engine.PlaceOrder(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusCreated, order)
}

func (s *Server) handleClosePosition(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		writeError(w, http.StatusBadRequest, errors.New("missing position id"))
		return
	}

	trade, err := s.engine.ClosePosition(r.Context(), id, models.CloseReasonManual)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusOK, trade)
}

func (s *Server) handleSignal(w http.ResponseWriter, r *http.Request) {
	var signal models.Signal
	if err := json.NewDecoder(r.Body).Decode(&signal); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}

	order, err := s.engine.ProcessSignal(r.Context(), signal)
	if err != nil {
		if strings.Contains(err.Error(), "hold signal") {
			writeJSON(w, http.StatusOK, map[string]string{"action": "none", "reason": err.Error()})
			return
		}
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusCreated, order)
}

func (s *Server) handleRiskStatus(w http.ResponseWriter, r *http.Request) {
	status, err := s.engine.RiskStatus(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, status)
}

func (s *Server) handleRiskReset(w http.ResponseWriter, r *http.Request) {
	if !s.cfg.IsDemo() {
		writeError(w, http.StatusForbidden, errors.New("risk reset only allowed in demo mode"))
		return
	}
	account, err := s.engine.GetAccount(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	s.engine.Risk().ResetDaily(account.Balance)
	s.logger.Info("demo risk daily reset", "balance", account.Balance)
	status, _ := s.engine.RiskStatus(r.Context())
	writeJSON(w, http.StatusOK, status)
}

func (s *Server) handleQuote(w http.ResponseWriter, r *http.Request) {
	symbol := r.PathValue("symbol")
	quote, err := s.engine.GetQuote(r.Context(), symbol)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, quote)
}

func (s *Server) handleBrokerStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"active_broker": s.engine.Broker().Name(),
		"mode":          s.cfg.Mode,
		"browser":       s.browser.Status(),
	})
}

func (s *Server) handleBrowserEnable(w http.ResponseWriter, r *http.Request) {
	_ = s.browser.EnableBridge(r.Context())
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "enabled",
		"message": "Browser automation enabled. Start: python strategy/browser_bridge.py",
	})
}

func (s *Server) handleBrowserSync(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Symbol  string  `json:"symbol"`
		Bid     float64 `json:"bid"`
		Ask     float64 `json:"ask"`
		Balance float64 `json:"balance"`
		Equity  float64 `json:"equity"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	quote := models.Quote{
		Symbol: body.Symbol,
		Bid:    body.Bid,
		Ask:    body.Ask,
		Spread: body.Ask - body.Bid,
	}
	if err := s.browser.SyncQuote(r.Context(), quote, body.Balance, body.Equity); err != nil {
		writeError(w, http.StatusBadGateway, err)
		return
	}
	if s.demo != nil && body.Bid > 0 && body.Ask > 0 {
		symbol := body.Symbol
		if symbol == "" {
			symbol = s.cfg.Trading.DefaultSymbol
		}
		s.demo.SyncQuote(symbol, body.Bid, body.Ask, body.Balance, body.Equity)
		s.logger.Info("demo engine synced from exness",
			"symbol", symbol, "bid", body.Bid, "ask", body.Ask, "balance", body.Balance)
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "synced"})
}

func (s *Server) handleControlStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.engine.Control().Status())
}

func (s *Server) handleControlEnable(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Reason string `json:"reason"`
		By     string `json:"by"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body.By == "" {
		body.By = "api"
	}
	state := s.engine.Control().Enable(body.By, body.Reason)
	s.logger.Info("trading enabled", "by", state.ChangedBy, "reason", state.Reason)
	writeJSON(w, http.StatusOK, state)
}

func (s *Server) handleControlDisable(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Reason string `json:"reason"`
		By     string `json:"by"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body.By == "" {
		body.By = "api"
	}
	state := s.engine.Control().Disable(body.By, body.Reason)
	s.logger.Info("trading disabled", "by", state.ChangedBy, "reason", state.Reason)
	writeJSON(w, http.StatusOK, state)
}

// handleControlStopAll is the emergency kill switch: disable new orders and
// best-effort close every open position, regardless of the current gate state.
func (s *Server) handleControlStopAll(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Reason string `json:"reason"`
		By     string `json:"by"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body.By == "" {
		body.By = "api"
	}
	if body.Reason == "" {
		body.Reason = "stop-all"
	}
	state := s.engine.Control().Disable(body.By, body.Reason)
	s.logger.Warn("STOP-ALL triggered", "by", state.ChangedBy, "reason", state.Reason)

	closed, closeErr := s.engine.CloseAllPositions(r.Context(), models.CloseReasonManual)
	resp := map[string]any{
		"control":        state,
		"closed_trades":  closed,
	}
	if closeErr != nil {
		resp["close_error"] = closeErr.Error()
	}
	writeJSON(w, http.StatusOK, resp)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}
