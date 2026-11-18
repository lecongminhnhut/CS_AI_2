# Thực nghiệm (mục 4.5)

Thư mục này chứa toàn bộ phần 4.5: bộ puzzle, chương trình chạy thực nghiệm headless, tổng hợp kết quả và kiểm thử tích hợp. Mọi lệnh chạy từ thư mục `Source/`. Chỉ cần thư viện chuẩn của Python; `matplotlib` là tùy chọn để vẽ biểu đồ.

## Cần có trước khi chạy

Runner chỉ gọi API công khai theo `TEAM_CONVENTIONS.md`:

| Module | Hàm dùng |
| --- | --- |
| `griductive/models.py` (4.2) | `load_puzzle` |
| `griductive/engine.py` (4.1) | `GameEngine.get_public_state`, `submit_verdict` |
| `griductive/agent.py` (4.4) | `next_move` |
| `griductive/encoder.py` (4.2) | `encode` (chỉ để lấy số biến/clause cho báo cáo) |
| `griductive/uniqueness.py` (4.4) | `check_uniqueness` |
| `griductive/sat.py`, `semantics.py`, `regions.py` | dùng trong test tích hợp |

Nếu module nào còn thiếu, runner ghi lần chạy đó là `ERROR` kèm lý do, còn test tương ứng được SKIP.

## Các file

| File | Vai trò |
| --- | --- |
| `../puzzles/puzzle_3x3_00[1-5].json`, `puzzle_4x4_00[1-5].json` | Bộ chuẩn: nghiệm duy nhất, giải hết được bằng suy luận no-guess. GUI cũng nạp các file này. |
| `stress/puzzle_5x5_00[1-2].json` | Ca stress 5×5. Để riêng vì GUI nạp mọi file trong `puzzles/`, mà `SUPPORTED_GRID_SIZES` mặc định chỉ có `(3, 4)`. |
| `fixtures/fixture_3x3_stuck.json` | Toàn bộ clue có nghiệm duy nhất, nhưng suy luận bị STUCK sau 2 bước. |
| `fixtures/fixture_4x4_ambiguous.json` | Toàn bộ clue có nhiều nghiệm, suy luận bị STUCK. |
| `fixtures/fixture_3x3_inconsistent.json` | Clue mở ở bước 1 mâu thuẫn KB, kỳ vọng INCONSISTENT. |
| `generate_puzzles.py` | Sinh lại bộ puzzle (tất định theo seed) hoặc kiểm tra bằng `--check`. |
| `oracle.py` | Bộ giải đối chứng độc lập (backtracking, không dùng CNF/DPLL) để kiểm tra puzzle và đối chiếu kết quả. |
| `run.py` | Runner headless, có timeout. |
| `summarize.py` | Tạo `summary.md` và biểu đồ từ một thư mục kết quả. |
| `tests/test_integration.py` | Kiểm thử tích hợp theo mục 11 của quy ước. |

Bộ puzzle phủ đủ 6 loại clue (FACT, SAME, DIFFERENT, EXACTLY, AT_LEAST, AT_MOST) và 6 loại region, gồm hai extension `CORNERS` và `BOUNDARY`.

## Cách chạy

```sh
cd Source
python benchmark/generate_puzzles.py --check     # kiểm tra bộ puzzle (không cần module nhóm)
python -m unittest discover -s benchmark/tests -t . -v
python benchmark/run.py                          # 15 puzzle × 3 lần, timeout 60 s mỗi lần
```

Tùy chọn của `run.py`:

- `--repeats N`: số lần lặp mỗi puzzle (mặc định 3; runtime báo trung vị).
- `--timeout-ms MS`: giới hạn mỗi lần chạy (mặc định 60000; `0` là không giới hạn).
- `--puzzles a.json b/*.json`: chạy một phần bộ puzzle.
- `--solver-config TÊN`: nhãn cấu hình ghi vào cột `solver_config`. Khi so sánh nhiều cấu hình, chạy mỗi cấu hình một lần trên **cùng bộ puzzle mặc định**.
- `--skip-uniqueness`: bỏ bước kiểm tra uniqueness.

Dùng `py` thay `python` trên Windows nếu cần.

## Kết quả

Mỗi lần chạy tạo `benchmark/results/<thời điểm>/`. Nên đưa `benchmark/results/` vào `.gitignore` và chỉ giữ bản dùng cho báo cáo.

| File | Nội dung |
| --- | --- |
| `results.csv` | Một dòng mỗi lần chạy, header đúng mục 10 của quy ước. |
| `traces/<run_id>.jsonl` | Trace JSON Lines của các bước ACCEPTED (mục 14.4). |
| `run_log.jsonl` | Chi tiết từng lần chạy: kết quả, lỗi và traceback, cờ `partial_metrics`, số query theo mục đích. |
| `puzzle_checks.csv` | `check_uniqueness` của nhóm so với oracle độc lập. |
| `environment.json` | Python, hệ điều hành, CPU, timeout và `solver_config`, để ghi vào báo cáo. |
| `summary.md`, `chart_*.png` | Bảng theo puzzle, trung bình theo kích thước, bảng thất bại, uniqueness và biểu đồ. |

Các chỉ số yêu cầu ở mục 4.5 của đề nằm ở các cột sau:

| Đề yêu cầu | Cột |
| --- | --- |
| Biến chính và biến phụ | `num_primary_variables`, `num_auxiliary_variables` |
| Số clause CNF | `num_clauses` (KB công khai cuối cùng) |
| Số SAT call | `sat_calls` |
| Decisions, propagations, backtracks | cùng tên, cộng dồn mọi query của lần chạy |
| Số bước suy luận | `deduction_steps` (số verdict ACCEPTED) |
| Runtime | `runtime_ms` |

## Quy tắc đo

- Mỗi lần chạy diễn ra trong một worker process riêng (spawn), nên timeout dừng được kể cả khi một lần solve chưa trả về.
- Runtime dùng `perf_counter` và chỉ tính thời gian gọi `next_move` và `submit_verdict`. Không tính thời gian load/validate puzzle, uniqueness, đếm CNF cho báo cáo và ghi file.
- `sat_calls` và các bộ đếm cộng từ `query_log`, gồm query của `next_move` và query xác minh của engine. Mỗi kết quả chỉ thu một lần và không cộng lại từ trace.
- TIMEOUT và ERROR vẫn giữ dòng trong CSV, ghi các bộ đếm đã thu được và đặt `partial_metrics: true` trong `run_log.jsonl`. Lỗi xảy ra trước khi bắt đầu suy luận (import/load) thì để trống thay vì ghi 0.
- Nếu agent đề xuất một verdict mà engine không chấp nhận, lần chạy đó ghi ERROR (agent và engine không khớp) thay vì lặp vô hạn.
- STUCK và INCONSISTENT ở các fixture là kết quả mong đợi. Bảng thất bại trong `summary.md` có cột "Khớp kỳ vọng" để phân biệt.
