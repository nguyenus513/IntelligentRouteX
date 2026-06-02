# Báo Cáo Đồ Án: IntelligentRouteX

## 1. Tổng Quan Hệ Thống

IntelligentRouteX là hệ thống tối ưu điều phối giao hàng theo thời gian thực. Hệ thống không chỉ giải bài toán định tuyến tĩnh một lần, mà hoạt động như một bộ điều phối liên tục: nhận đơn mới, cập nhật vị trí tài xế, giữ ổn định các tuyến đang chạy, tối ưu lại phần còn có thể thay đổi và xuất kết quả qua API, dashboard, events, artifacts và metrics.

Thông điệp chính nên dùng trong báo cáo:

> IntelligentRouteX kết hợp multi-solver seed generation, rolling-horizon dispatch, BigData-lite ingestion, adaptive ML-guided refinement và dominance guard để tạo tuyến giao hàng ổn định, khả thi và có khả năng mở rộng cho demo/pilot logistics.

Các thành phần chính:

- **Frontend/dashboard:** React/Vite dashboard trong `playground/`, dùng để demo bản đồ, benchmark, API sandbox và decision trace.
- **Backend API:** Spring Boot, cung cấp static dispatch, live rolling dispatch, rescue, BigData-lite, artifacts, events, metrics.
- **Optimization core:** `DispatchV2Core`, chạy pipeline tối ưu nhiều giai đoạn.
- **Runtime:** queue, job store, result store, live session store, artifact store, metrics registry.
- **External solvers:** VROOM, OR-Tools, PyVRP dùng làm seed/benchmark khi runtime có sẵn.
- **Adaptive ML sidecars:** Tabular, RouteFinder, GreedRL, Forecast hỗ trợ xếp hạng, đề xuất action, phân tích rủi ro; không được phép vượt qua evaluator/dominance guard.
- **BigData-lite:** batch API, in-memory queue, pagination, dead-letter, requeue, JSONL file-lake sink.

## 2. Bài Toán Hệ Thống Giải Quyết

Hệ thống hướng tới bài toán giao hàng thực tế, phức tạp hơn static VRP:

- Đơn hàng đến liên tục, không biết trước toàn bộ.
- Tài xế di chuyển, online/offline, trạng thái thay đổi theo thời gian.
- Tuyến đã giao cho tài xế không thể bị đổi tùy tiện.
- Điểm pickup phải đứng trước dropoff.
- Xe/tài xế có giới hạn tải, thời gian, SLA/deadline.
- Một số đơn có thể giữ trong buffer ngắn để ghép cụm, nhưng không được bị quên.
- Hệ thống phải cân bằng giữa chất lượng tuyến, độ trễ, khả năng đáp ứng realtime và độ ổn định route.

Vì vậy, hệ thống dùng mô hình **stateful realtime dispatch orchestrator** thay vì chỉ dùng một solver tĩnh.

## 3. Kiến Trúc Tổng Thể

Luồng tổng quát:

```text
Client/Dashboard/API caller
        ↓
Spring Boot API /api/v1
        ↓
Runtime queue + store + validation + idempotency
        ↓
DispatchV2Core optimization pipeline
        ↓
Optional external solvers / ML workers / OSRM
        ↓
Dominance guard + executor
        ↓
Result + events + artifacts + metrics + dashboard visualization
```

Các endpoint chính:

- **Static dispatch:** `POST /api/v1/static/dispatch`.
- **Async jobs:** tạo job, lấy trạng thái, lấy kết quả, cancel, events, artifacts.
- **Live rolling:** start/stop session, thêm order, cập nhật location tài xế, chạy cycle, đọc state/events.
- **Rescue:** tạo rescue job, đọc kết quả rescue.
- **BigData-lite:** batch ingest, batch items pagination, dead-letter, requeue, metrics.
- **Runtime/metrics:** health, runtime state, queue depth, workers, metrics.

Các package quan trọng:

- `src/main/java/com/routechain/api`: controller API demo/dashboard/live.
- `src/main/java/com/routechain/api/v1`: production API v1.
- `src/main/java/com/routechain/runtime`: queue, stores, metrics, artifacts.
- `src/main/java/com/routechain/v2`: optimization engine.
- `src/main/java/com/routechain/v2/streaming`: Kafka optional + BigData sink.
- `playground`: dashboard React/Vite.

## 4. Pipeline Tối Ưu Trong `DispatchV2Core`

Pipeline chính gồm các stage sau:

1. **Rolling order buffer:** merge đơn đến hạn, quyết định giữ/chạy ngay/micro-batch/reoptimize.
2. **ETA/context:** tính ETA, khoảng cách, traffic/weather/freshness nếu có.
3. **Pair graph:** tạo quan hệ tương thích giữa các đơn.
4. **Micro-cluster:** gom cụm đơn gần nhau hoặc cùng corridor.
5. **Bundle pool:** sinh candidate bundle nhiều đơn.
6. **Pickup anchor:** chọn điểm neo pickup tốt.
7. **Driver shortlist/rerank:** lọc tài xế phù hợp nhất.
8. **Route proposal pool:** tạo nhiều phương án route.
9. **Scenario evaluation:** chấm điểm route theo distance, late, risk, stability.
10. **Global selector:** chọn tổ hợp assignment tốt nhất.
11. **Dispatch executor:** xuất assignment cuối, cập nhật active fleet state.
12. **Post-dispatch hardening:** dominance guard, replay/artifact/metrics, no-regress safety.

Pipeline này cho phép hệ thống vừa nhanh, vừa an toàn, vừa có khả năng cải thiện chất lượng qua nhiều candidate.

## 5. Cách Hoạt Động Theo Từng Chế Độ

### 5.1 Static Dispatch

Static dispatch nhận toàn bộ danh sách đơn/tài xế, sau đó:

```text
Input orders/drivers
 → validate
 → tạo seed bằng IRX native/external solvers
 → cải tiến bằng IRX refinement
 → so sánh bằng objective comparator
 → dominance guard
 → trả routes/metrics/diagnostics
```

Mục tiêu static dispatch:

- Tối đa coverage.
- Không vi phạm hard constraints.
- Giảm số đơn trễ và tổng thời gian trễ.
- Giảm số xe/tuyến khi có thể.
- Giảm tổng quãng đường.
- Giữ runtime trong budget.

### 5.2 Live Rolling Dispatch

Live dispatch hoạt động theo chu kỳ. Mỗi cycle nhận thêm đơn mới, vị trí tài xế, trạng thái route và quyết định:

- `DISPATCH_NOW`: giao ngay khi đơn gấp hoặc ít cơ hội ghép.
- `HOLD_SHORT`: giữ ngắn hạn nếu còn slack và có cơ hội bundle.
- `MICRO_BATCH`: gom cụm đơn gần nhau để tối ưu tốt hơn.
- `REOPTIMIZE_ACTIVE_ROUTE`: chèn/sửa route đang chạy nếu có lợi và an toàn.

Điểm quan trọng: live dispatch không được phá route đang chạy. Freeze policy giữ các stop đã commit hoặc đang thực hiện.

### 5.3 Rescue Dispatch

Rescue dùng khi tuyến có nguy cơ trễ hoặc driver gặp vấn đề:

```text
Detect risk/late
 → freeze current/unsafe-to-change stops
 → repair remaining route
 → evaluate before/after late
 → dominance guard
 → output rescued routes
```

Kết quả rescue cần báo cáo các chỉ số: `beforeLate`, `afterLate`, `lateNotWorse`, `rescuedRouteCount`, `rescueDominanceGuard`.

### 5.4 BigData-lite

BigData-lite là cách hệ thống xử lý input lớn ở mức demo/pilot mà không cần Kafka/Spark:

```text
POST batch
 → validate/normalize/dedupe
 → queue admission
 → worker lifecycle
 → result summary
 → paginated item access
 → dead-letter/requeue/metrics
```

Nó phù hợp cho đồ án vì dễ chạy local, dễ demo, có cơ chế backpressure, dead-letter và metrics rõ ràng.

## 6. Các Thuật Toán Chính

### 6.1 Nearest Feasible Driver

Thuật toán chọn tài xế gần nhất nhưng vẫn thỏa điều kiện tải, thời gian, pickup/dropoff và SLA.

Ưu điểm:

- Rất nhanh.
- Dễ dùng làm baseline.
- Phù hợp fast path khi cần kết quả ngay.

Nhược điểm:

- Dễ tối ưu cục bộ.
- Không nhìn được lợi ích bundle nhiều đơn.
- Có thể làm mất cân bằng tải tài xế.

Vai trò trong IRX: tạo incumbent/baseline nhanh, không phải phương án duy nhất.

### 6.2 Regret Insertion

Regret insertion đo mức “tiếc nuối” nếu không chèn đơn vào vị trí tốt nhất hiện tại.

Công thức khái niệm:

```text
regret(order) = cost(second_best_position) - cost(best_position)
```

Đơn có regret cao được ưu tiên vì nếu bỏ lỡ vị trí tốt nhất, chi phí sau này tăng mạnh.

Ưu điểm:

- Tốt hơn greedy đơn giản.
- Hữu ích cho VRPTW/PDPTW.
- Cân bằng giữa chi phí hiện tại và rủi ro tương lai.

### 6.3 Beam Search / Top-K Pruning

Beam search mở rộng nhiều candidate nhưng chỉ giữ top-K candidate tốt nhất ở mỗi bước.

Ưu điểm:

- Tốt hơn greedy vì xem nhiều nhánh.
- Nhanh hơn exhaustive search.
- Phù hợp realtime vì kiểm soát được budget.

Trong IRX, Top-K còn được adaptive ML hỗ trợ để ưu tiên move đáng thử trước.

### 6.4 ALNS / LNS Destroy-Repair

Large Neighborhood Search phá một phần route rồi sửa lại:

```text
Current solution
 → destroy: remove weak/overloaded/related orders
 → repair: reinsert by regret/feasible insertion
 → evaluate
 → accept if improves or passes safety policy
```

Các operator có thể gồm:

- Shaw related removal.
- Weak bundle removal.
- Suffix destroy/repair.
- Route split/merge.
- Regret-3 insertion.
- Restaurant-aware insertion.
- Route-shape-aware reinsertion.

Ưu điểm:

- Thoát local optimum tốt.
- Phù hợp bài toán nhiều ràng buộc.
- Có thể chạy trong budget giới hạn.

### 6.5 Pickup-Delivery LNS

PD-LNS tối ưu ở cấp pickup/dropoff sequence, giữ ràng buộc:

```text
pickup(order_i) phải đứng trước dropoff(order_i)
capacity không vượt giới hạn
frozen stop không bị phá
```

Đây là thuật toán quan trọng vì hệ giao hàng không chỉ là đi qua điểm, mà có quan hệ pickup/dropoff bắt buộc.

### 6.6 Dominance Guard

Dominance guard là lớp an toàn cuối. Nó không cho phép kết quả cuối tệ hơn baseline mạnh nhất theo thứ tự ưu tiên:

1. Coverage cao hơn.
2. Hard violations thấp hơn.
3. Late count thấp hơn.
4. Total lateness thấp hơn.
5. Vehicle/route count thấp hơn.
6. Distance thấp hơn.
7. Runtime thấp hơn.

Nhờ guard này, ML hoặc local search có thể đề xuất candidate nhưng không được làm hỏng kết quả cuối.

### 6.7 Adaptive ML Policy

Adaptive ML trong hệ thống không thay thế solver. Nó hỗ trợ:

- Xếp hạng seed source.
- Phân bổ budget cho operator.
- Sắp xếp candidate move trước khi evaluator tính toán nặng.
- Chọn action live/rescue qua GreedRL.
- Cung cấp route/edge/sequence candidate qua RouteFinder.
- Chấm điểm tabular candidate qua Tabular model.
- Forecast dùng cho risk diagnostics trong live/rescue.

Nguyên tắc an toàn:

- ML chỉ gợi ý, không có quyền bỏ qua constraint.
- Evaluator quyết định accept/reject.
- Dominance guard quyết định final no-regress.

## 7. Vì Sao Chọn Kiến Trúc Hybrid

Không có một thuật toán duy nhất tối ưu cho mọi trường hợp:

| Cách tiếp cận | Ưu điểm | Nhược điểm | Vai trò trong IRX |
|---|---|---|---|
| Greedy/nearest | Nhanh, đơn giản | Dễ kẹt local optimum | Baseline/fast path |
| Regret insertion | Tốt cho chèn đơn | Vẫn heuristic | Repair/seed |
| Beam search | Xem nhiều nhánh | Cần giới hạn K | Candidate generation |
| VROOM/OR-Tools/PyVRP | Solver mạnh | Phụ thuộc runtime, có latency | External seed/benchmark |
| LNS/ALNS | Cải thiện chất lượng tốt | Cần budget | IRX refinement |
| ML policy | Ưu tiên search thông minh | Không đảm bảo feasibility | Ranking/controller |
| Dominance guard | Chống regression | Không tự sinh lời giải | Safety layer |

Do đó, IRX dùng hybrid stack:

```text
Fast heuristic → multi-solver seed → adaptive refinement → dominance guard
```

Cách này phù hợp đồ án vì vừa có nền tảng thuật toán, vừa có kiến trúc hệ thống, vừa có bằng chứng benchmark.

## 8. Cân Bằng Tải Và Backpressure

Runtime queue dùng các lane ưu tiên:

| Lane | Độ ưu tiên | Ý nghĩa |
|---|---:|---|
| `RESCUE` | 0 | Cứu tuyến, quan trọng nhất |
| `LIVE` | 1 | Điều phối realtime |
| `FAST` | 2 | Job nhanh |
| `QUALITY` | 3 | Job cần chất lượng cao hơn |
| `BENCHMARK` | 4 | Benchmark, ít khẩn cấp nhất |

Thiết kế này giúp hệ thống không để benchmark hoặc job chất lượng cao chiếm tài nguyên của rescue/live dispatch.

Cơ chế chống quá tải:

- Queue admission.
- Priority lane routing.
- Backpressure response.
- Dead-letter khi lỗi hoặc quá tải.
- Requeue để xử lý lại.
- Metrics theo queue depth/job/event/artifact.

## 9. Hệ Thống Dùng Gì Thay Vì Kafka?

Trong trạng thái mặc định, hệ thống **không cần Kafka** để chạy demo. Thay vào đó dùng:

- REST API cho request/response chính.
- In-memory queue cho runtime jobs.
- In-memory stores cho job/result/live-session.
- SSE/event endpoints hoặc polling để theo dõi events.
- BigData-lite batch API cho input lớn.
- Dead-letter/requeue API cho lỗi.
- JSONL file-lake sink cho dữ liệu kết quả/training trace khi bật file sink.
- Artifact store để lưu evidence/output.

Kafka vẫn tồn tại như tùy chọn trong `DispatchKafkaConsumer`, `DispatchKafkaPublisher`, `DispatchKafkaConfiguration`, nhưng chỉ hoạt động khi bật cấu hình streaming. Vì vậy, khi báo cáo nên nói:

> Hệ thống dùng BigData-lite và runtime queue mặc định để giảm độ phức tạp triển khai. Kafka là optional integration cho môi trường production/distributed, không phải dependency bắt buộc của demo đồ án.

So sánh:

| Tiêu chí | BigData-lite hiện tại | Kafka |
|---|---|---|
| Cài đặt local | Dễ | Phức tạp hơn |
| Demo đồ án | Phù hợp | Có thể quá nặng |
| Backpressure/DLQ | Có mức runtime/API | Mạnh hơn |
| Distributed scale | Giới hạn | Tốt |
| Replay stream lớn | Giới hạn | Tốt |
| Chi phí vận hành | Thấp | Cao hơn |

## 10. Mức Độ Phù Hợp Với Big Data

Hệ thống phù hợp mức **BigData-lite**, nghĩa là:

- Có thể ingest batch nhiều item.
- Có validate/dedupe.
- Có queue admission/backpressure.
- Có pagination thay vì trả response khổng lồ.
- Có dead-letter/requeue.
- Có metrics/artifacts.
- Có JSONL output để phân tích offline.

Tuy nhiên, không nên claim hệ thống hiện tại là Kafka/Spark/Flink distributed big data hoàn chỉnh. Hướng mở rộng production:

- Thay in-memory store bằng PostgreSQL/Redis.
- Thay in-memory queue bằng Kafka/RabbitMQ/Pulsar.
- Dùng S3/MinIO/HDFS cho data lake.
- Dùng Spark/Flink cho analytics/stream processing.
- Scale workers bằng Kubernetes.
- Tách solver workers thành service độc lập.

## 11. Bảo Mật Và Độ Tin Cậy

Các cơ chế có thể trình bày:

- `X-Api-Key`, `X-Tenant-Id` cho security MVP.
- `Idempotency-Key` cho endpoint tạo tài nguyên, tránh submit trùng.
- Rate-limit/backpressure để bảo vệ runtime.
- Artifact access guard để chặn path traversal.
- Stable error envelope với mã lỗi rõ ràng.
- Job lifecycle: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`.
- Dead-letter/requeue để lỗi không bị mất dấu.

## 12. Benchmark Và Bằng Chứng Hiệu Quả

Các metric nên dùng:

- **Coverage:** số đơn được phục vụ.
- **Hard violations:** lỗi capacity, pickup/dropoff, frozen stop.
- **Late count:** số đơn trễ.
- **Total lateness:** tổng phút trễ.
- **Vehicle/route count:** số tuyến/tài xế dùng.
- **Distance:** tổng quãng đường.
- **Runtime:** thời gian xử lý.
- **Dominance failures:** số lần kết quả tệ hơn baseline.

Bằng chứng đã có trong repo:

- ML-guided PD-LNS final 20-case: cải thiện best seed ở `19/20` case, total distance gain `620.4 km`, không late regression, không coverage regression, không pickup/dropoff/capacity violation.
- Tri-model fusion 5-case: Tabular/RouteFinder/GreedRL đều có contribution, fusion không tệ hơn best single model, total fusion gain `98.3 km`.
- BigData-lite gate: có evidence batch `100` và `1000` item, backpressure không làm crash hệ thống.
- Production API core gate: kiểm tra API contract, queue/store abstraction, events, artifacts, observability.

Lưu ý khi bảo vệ:

- Không nói ML luôn tốt hơn heuristic.
- Không nói hệ thống đã production distributed Kafka/Spark nếu chưa triển khai.
- Không nói latency/churn/SLA win nếu chưa có baseline đo công bằng.
- Chỉ claim theo artifact/evidence trong repo.

## 13. Sơ Đồ Gợi Ý Cho Slide

### 13.1 Sơ Đồ Kiến Trúc

```text
React Dashboard / API Client
        |
        v
Spring Boot API Gateway (/api/v1)
        |
        +--> Runtime Queue + Stores + Metrics
        |
        v
DispatchV2Core Pipeline
        |
        +--> OSRM / Traffic / Weather Context
        +--> VROOM / OR-Tools / PyVRP Seeds
        +--> Adaptive ML Workers
        |
        v
Dominance Guard + Executor
        |
        v
Routes + Events + Artifacts + BigData-lite JSONL
```

### 13.2 Sơ Đồ Thuật Toán

```text
Orders + Drivers
   ↓
ETA/context + pair graph
   ↓
Cluster + bundle generation
   ↓
Driver shortlist + route proposals
   ↓
Scenario evaluation
   ↓
Global selector
   ↓
LNS/repair/adaptive refinement
   ↓
Dominance guard
   ↓
Final dispatch result
```

### 13.3 Sơ Đồ Live Dispatch

```text
New order / driver telemetry
        ↓
Rolling buffer
        ↓
Decision mode: dispatch now / hold / micro-batch / reoptimize
        ↓
Freeze current stops
        ↓
Repair active route safely
        ↓
Publish route update + event timeline
```

## 14. Dàn Ý Thuyết Trình

1. **Giới thiệu bài toán:** giao hàng realtime khác static VRP như thế nào.
2. **Mục tiêu hệ thống:** tối ưu tuyến, giảm trễ, giữ ổn định route, hỗ trợ batch lớn.
3. **Kiến trúc tổng quan:** dashboard, API, runtime, optimizer, BigData-lite.
4. **Pipeline tối ưu:** giải thích từng stage của `DispatchV2Core`.
5. **Thuật toán:** greedy, regret insertion, beam search, LNS/ALNS, PD-LNS, dominance guard, adaptive ML.
6. **Live dispatch/rescue:** rolling horizon, freeze policy, rescue no-regress.
7. **BigData-lite:** vì sao không dùng Kafka mặc định, cơ chế queue/backpressure/DLQ.
8. **Benchmark:** metric, evidence, bảng so sánh solver.
9. **Demo:** dashboard, API sandbox, live cycle, benchmark table.
10. **Hạn chế/hướng phát triển:** Kafka/Spark, persistent DB, distributed workers, Kubernetes.

## 15. Câu Trả Lời Nhanh Khi Giảng Viên Hỏi

**Hỏi: Vì sao không chỉ dùng OR-Tools?**

Vì OR-Tools mạnh cho bài toán tĩnh nhưng live dispatch cần rolling buffer, freeze policy, rescue, dominance guard, BigData-lite và nhiều quyết định runtime. IRX dùng OR-Tools như một seed/baseline trong hybrid portfolio, không thay thế toàn bộ hệ thống.

**Hỏi: Vì sao không dùng Kafka?**

Kafka phù hợp distributed streaming lớn, nhưng đồ án cần chạy local, dễ demo và kiểm soát. IRX dùng BigData-lite với REST batch, in-memory queue, backpressure, dead-letter và JSONL sink. Kafka được giữ optional cho production extension.

**Hỏi: ML có quyết định route cuối không?**

Không. ML chỉ hỗ trợ ranking/action/candidate. Evaluator kiểm tra constraint, dominance guard bảo vệ final result.

**Hỏi: Hệ thống đảm bảo không giao dropoff trước pickup thế nào?**

Pickup/dropoff precedence là hard constraint trong evaluator/repair/PD-LNS. Candidate vi phạm bị reject và benchmark ghi nhận pickup/dropoff violations.

**Hỏi: Cân bằng tải tài xế thế nào?**

Hệ thống dùng driver shortlist/rerank, route proposal, scenario evaluation và global selector. Queue runtime cũng cân bằng ưu tiên job bằng lane: rescue/live/fast/quality/benchmark.

**Hỏi: Hệ thống mở rộng Big Data thế nào?**

Hiện là BigData-lite: batch, queue admission, pagination, DLQ, metrics, JSONL. Production có thể mở rộng bằng Kafka, Redis/Postgres, S3/MinIO, Spark/Flink, Kubernetes workers.

## 16. File Và Nguồn Tham Chiếu Trong Repo

- `README.md`: mô tả tổng quan, quick start, validation.
- `docs/ARCHITECTURE.md`: kiến trúc backend/API/runtime.
- `docs/API_REFERENCE.md`: endpoint và contract API.
- `docs/DYNAMIC_DISPATCH.md`: live dispatch/rescue/dynamic ML.
- `docs/BIGDATA_LITE_API.md`: BigData-lite flow.
- `docs/ADAPTIVE_ML_POLICY.md`: adaptive policy, ML role, safety model.
- `docs/BENCHMARKS.md`: benchmark principles và evidence.
- `docs/REPORT_GUIDE.md`: checklist báo cáo/demo.
- `src/main/java/com/routechain/v2/DispatchV2Core.java`: pipeline tối ưu chính.
- `src/main/java/com/routechain/runtime/queue/QueueRouter.java`: lane/priority queue.
- `src/main/java/com/routechain/runtime/queue/InMemoryDispatchQueue.java`: queue runtime mặc định.
- `src/main/java/com/routechain/v2/streaming/FileLakeDispatchBigDataSink.java`: JSONL file-lake sink.
- `src/main/java/com/routechain/v2/streaming/DispatchKafkaConsumer.java`: Kafka optional consumer.
- `src/main/java/com/routechain/v2/streaming/DispatchKafkaPublisher.java`: Kafka optional publisher.

## 17. Kết Luận

IntelligentRouteX là một hệ thống điều phối giao hàng realtime theo hướng hybrid optimization. Giá trị chính của hệ thống không nằm ở một thuật toán riêng lẻ, mà ở cách kết hợp nhiều lớp: API production, runtime queue, rolling horizon, multi-solver seed, adaptive refinement, dominance guard, rescue, BigData-lite và dashboard demo. Thiết kế này phù hợp đồ án vì vừa thể hiện kiến thức hệ thống phân tán nhẹ, vừa có thuật toán tối ưu, vừa có bằng chứng benchmark và khả năng trình diễn thực tế.
