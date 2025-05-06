# 모니터링 및 로깅 인프라

이 디렉토리에는 샘플 마이크로 애플리케이션에 대한 모니터링 및 로깅 인프라 설정이 포함되어 있습니다.

## 구성 요소

- **Prometheus**: 메트릭 수집 및 저장
- **Loki**: 로그 수집 및 저장
- **Promtail**: 로그 수집 에이전트
- **Tempo**: 분산 추적 시스템
- **Grafana**: 데이터 시각화

## 시작하기

모든 서비스를 실행하려면 다음 명령어를 사용하세요:

```bash
docker-compose up -d
```

## 접속 정보

- **Grafana**: http://localhost:3000 (admin / password)
- **Prometheus**: http://localhost:9090
- **Loki**: http://localhost:3100
- **Tempo**: http://localhost:3200

## 애플리케이션 연동 방법

### 메트릭 수집 (Prometheus)

애플리케이션에서 Prometheus 메트릭을 노출하려면 `/metrics` 엔드포인트를 구현하고 포트 8080에서 실행하세요.

### 로그 수집 (Loki)

애플리케이션 로그를 `/var/log/app/*.log` 경로에 저장하면 Promtail이 자동으로 수집합니다.

### 분산 추적 (Tempo)

애플리케이션에서 OpenTelemetry, Zipkin 또는 Jaeger 프로토콜을 사용하여 Tempo에 추적 데이터를 전송할 수 있습니다:

- OpenTelemetry: http://tempo:4318 (HTTP) 또는 tempo:4317 (gRPC)
- Zipkin: http://tempo:9411
- Jaeger: http://tempo:14268 (HTTP)

## 알림 설정

현재 설정에는 알림이 구성되어 있지 않습니다. 필요한 경우 Prometheus AlertManager를 추가하여 알림을 설정할 수 있습니다. 