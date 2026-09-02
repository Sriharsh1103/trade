FROM golang:1.22-alpine AS builder

WORKDIR /build
COPY backend/go.mod backend/go.sum ./
RUN go mod download
COPY backend/ ./
RUN CGO_ENABLED=0 go build -o /trader ./cmd/trader

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /trader /app/trader
EXPOSE 8080
ENTRYPOINT ["/app/trader"]
CMD ["--config", "/app/config/config.yaml"]
