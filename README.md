# Griductive · GUI và game (4.1)

Khi nhóm đã bổ sung đủ module chạy game và puzzle theo schema `1.0.0`, chạy từ thư mục gốc bằng Python 3.14. GUI dùng Three.js và font đi kèm, không cần npm hay tải thư viện từ mạng.

```sh
cd Source
py main.py
```

Dùng `python main.py` nếu máy không có lệnh `py`. Trình duyệt mặc định mở ở [http://127.0.0.1:8000](http://127.0.0.1:8000). Có thể chọn cổng bằng `--port 8080` hoặc chạy với `--no-browser`. Nếu thiếu file chạy game hoặc puzzle, lệnh báo danh sách cần bổ sung trước khi khởi động server.

## Nối phần của các thành viên

Các đường dẫn bên dưới tính từ `Source/`, trừ những mục ghi rõ là ở thư mục gốc. Dùng chữ ký, schema và enum từ mục 14–16 của [TEAM_CONVENTIONS.md](../TEAM_CONVENTIONS.md).

### 4.1 · GUI và game

Các file chính đã có. Người phụ trách cập nhật khi nối các phần của nhóm.

| File | Công việc |
| --- | --- |
| `main.py` | Kiểm tra các file tích hợp, nạp puzzle, khởi chạy server và mở trình duyệt. |
| `griductive/engine.py` | `GameEngine` giữ puzzle riêng, trả `get_public_state()`, kiểm tra `submit_verdict()` và xử lý `restart()`. |
| `griductive/gui/server.py` | Phục vụ giao diện và điều phối API theo phiên chơi. |
| `griductive/gui/team_session.py` | Nối engine và agent với GUI, ghi trace từ các verdict được chấp nhận. |
| `griductive/gui/web/` | Bố cục trong `index.html` và `style.css`, thao tác chơi trong `app.js`, hiệu ứng Three.js trong `board3d.js` và chân dung trong `portraits.js`. |
| `README.md`, `requirements.txt` | Tổng hợp hướng dẫn chạy và dependency của sản phẩm. |

Mục 4.1 cũng phụ trách `.gitignore` và `.gitattributes` ở thư mục gốc.

### 4.2 · CNF và dữ liệu chung

| File | Công việc |
| --- | --- |
| `griductive/models.py` | Bổ sung schema và enum dùng chung, gồm `Puzzle`, `PublicState`, `SatResult`, `VerdictResult` và các kiểu ở mục 14. Cài `load_puzzle()` và các hàm validation. |
| `griductive/regions.py` | Bổ sung hàm xử lý tọa độ, `resolve_region()` và `get_referenced_cell_ids()`. Hỗ trợ `CORNERS` và `BOUNDARY` để GUI tô sáng đúng ô. |
| `griductive/semantics.py` | Cài `evaluate_clue()` để kiểm tra trực tiếp clue trên một assignment đầy đủ. |
| `griductive/encoder.py` | Cài `encode()`, `encode_clue()`, `build_variable_map()` và bộ cấp phát biến phụ. `encode()` nhận `PublicState` và trả `EncodedKB`. |

`griductive/__init__.py` đã có file khởi tạo. Mục 4.2 phụ trách file này và phối hợp duy trì `TEAM_CONVENTIONS.md` ở thư mục gốc.

### 4.3 · DPLL SAT

| File | Công việc |
| --- | --- |
| `griductive/sat.py` | Bổ sung `solve(clauses, num_variables, assumptions=None)`. Cài DPLL, unit propagation, chọn nhánh và đếm thống kê. Trả `SatResult` theo kiểu của mục 4.2. |

### 4.4 · Agent và uniqueness

| File | Công việc |
| --- | --- |
| `griductive/agent.py` | Bổ sung `classify()`, `classify_all()` và `next_move()`. Dùng encoder và SAT để suy luận từ `PublicState`. Engine dùng `classify()` để kiểm tra verdict, còn GUI dùng `next_move()` cho Hint và Auto solve. |
| `griductive/uniqueness.py` | Bổ sung `check_uniqueness(puzzle)` để kiểm tra nghiệm của toàn bộ clue. Blocking clause dùng assignment của biến chính. |

### 4.5 · Bộ puzzle, kiểm thử và benchmark

| Vị trí | Công việc |
| --- | --- |
| `puzzles/*.json` | Thêm bộ puzzle schema `1.0.0`, có màn 3×3 và 4×4. Chuẩn bị ca mơ hồ, mâu thuẫn, đếm ở biên và hai region mở rộng theo mục 11. |
| `benchmark/` | Bổ sung chương trình chạy thực nghiệm headless, bộ kiểm thử và hướng dẫn chạy. Xuất kết quả CSV và trace JSON Lines theo mục 10. Nhóm có thể đặt tên file như `benchmark/run.py` và `benchmark/tests/test_integration.py`. |
| `requirements-dev.txt`, `pyproject.toml` | Bổ sung khi cần dependency kiểm thử hoặc cấu hình test, lint và format. |

### Cách các module nối với GUI

- `GameEngine` gọi `agent.classify(public_state, cell_id)` để kiểm tra verdict và chỉ reveal khi có chứng minh. Engine sở hữu dữ liệu ẩn và trả snapshot độc lập. `models.py` của 4.2 là nguồn định nghĩa kiểu và validation.
- `griductive/gui/team_session.py` dùng `models.load_puzzle`, `agent.next_move` và `regions.get_referenced_cell_ids`. GUI chuyển các kiểu công khai của nhóm thành dữ liệu hiển thị cho web. Hai extension ở chế độ tích hợp là `CORNERS` và `BOUNDARY` theo quy ước.
- Hợp đồng `MoveResult` chưa chứa ID clue dùng trong chứng minh. Hint ở chế độ tích hợp đánh dấu các clue đã mở để người chơi xem lại. Reveal chỉ đích đến mà agent tìm được.
- Deduction log ghi từng verdict `ACCEPTED`. `GET /api/trace` trên cùng phiên trình duyệt trả trace JSON Lines theo mục 10. Thống kê GUI tổng hợp từ truy vấn mà agent và engine trả về và chỉ hiển thị các chỉ số có dữ liệu.
