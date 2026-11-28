# Griductive Solver

Đồ án 2 môn Nhập môn Trí tuệ nhân tạo (CSC14003). Griductive là trò chơi suy luận trên trình duyệt, trong đó người chơi xác định từng nhân vật là Criminal hoặc Innocent. Bộ giải SAT dùng thuật toán DPLL để kiểm tra kết luận dựa trên các manh mối đã mở và trạng thái đã biết. Mỗi kết luận được chứng minh sẽ lật một thẻ và đưa manh mối mới vào lượt suy luận tiếp theo.

## Khởi chạy

Mở terminal tại thư mục chứa `main.py`. Trong bản nộp đã giải nén, đây là thư mục `Source/`. Nhóm dùng Python 3.14. Chương trình và bộ kiểm thử chạy bằng thư viện chuẩn Python, còn Three.js, phông chữ và hình ảnh đi kèm trong `griductive/gui/web/`.

```sh
python main.py
```

Trên Windows, có thể dùng `py main.py` nếu máy có trình khởi chạy `py`. Chương trình tự mở `http://127.0.0.1:8000/` trong trình duyệt. Nếu tab chưa mở, truy cập trực tiếp địa chỉ này.

Nếu cổng 8000 đang được dùng, chạy `python main.py --port 8080 --no-browser` rồi mở `http://127.0.0.1:8080/`. Nhấn Ctrl+C trong terminal để dừng máy chủ.

## Chơi và xem lời giải

1. Chọn màn trong Case library. Danh sách có 5 màn 3×3, 5 màn 4×4 và 2 màn 5×5.
2. Chọn thẻ đã mở để đọc manh mối trong Evidence. Bàn cờ tô sáng các ô được nhắc tới. Chọn một cụm từ gạch dưới để chỉ xem các ô tương ứng với cụm đó.
3. Chọn một thẻ úp, sau đó chọn Innocent hoặc Criminal. Thẻ lật khi dữ kiện đủ để chứng minh lựa chọn. Nếu cả hai kết luận vẫn có thể đúng, chương trình trả `NOT_PROVABLE`. Nếu dữ kiện chứng minh kết luận ngược lại, chương trình trả `CONTRADICTED`. Thẻ giữ nguyên trong cả hai trường hợp.

Hint đánh dấu các manh mối đã mở. Bấm tiếp Reveal để xác định ô có thể suy luận ở lượt hiện tại. Thẻ chỉ lật sau khi người chơi gửi kết luận và chương trình chấp nhận.

Auto solve tự thực hiện từng bước suy luận. Dùng Pause để tạm dừng và Restart case để đưa màn chơi về trạng thái ban đầu.

Deduction log hiển thị thống kê SAT và các lượt suy luận được chấp nhận. Mở từng lượt để xem các manh mối đang dùng, truy vấn SAT, kết luận và manh mối vừa lật. Nhật ký dạng JSON Lines có tại `/api/trace` trong cùng phiên trình duyệt.

Để xem các bước suy luận của một màn trong terminal, chạy trực tiếp mô-đun agent.

```sh
python -m griductive.agent puzzles/puzzle_3x3_001.json
```

## Kiểm thử và thực nghiệm

Chạy các lệnh sau từ thư mục chứa `main.py`.

```sh
python benchmark/generate_puzzles.py --check
python -m unittest discover -s benchmark/tests -t . -v
python benchmark/run.py
```

Hai lệnh đầu lần lượt xác minh dữ liệu bằng bộ giải đối chứng và chạy bộ kiểm thử cho mã hóa CNF, DPLL, agent, engine và chương trình thực nghiệm.

Benchmark mặc định chạy 15 bài toán, mỗi bài 3 lần với giới hạn 60 giây mỗi lượt. Bộ dữ liệu gồm 10 màn chuẩn, 2 màn 5×5 để đo tải và 3 ca kiểm tra các tình huống hết bước suy luận, có nhiều nghiệm hoặc có dữ kiện mâu thuẫn.

Để chạy một màn, dùng `python benchmark/run.py --puzzles puzzles/puzzle_3x3_001.json --repeats 1`. Để xuất biểu đồ, cài các gói tùy chọn bằng `python -m pip install -r requirements-dev.txt` trước khi chạy benchmark.

| Tệp trong `benchmark/results/<thời điểm>/` | Nội dung                                                                                                                                       |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `results.csv`                              | Trạng thái từng lượt, số biến chính và phụ, số mệnh đề CNF, số truy vấn SAT, số lần quyết định, lan truyền và quay lui, cùng số bước suy luận và thời gian chạy. |
| `traces/*.jsonl`                           | Các bước suy luận được chấp nhận trong từng lần chạy.                                                                                          |
| `puzzle_checks.csv`                        | Kết quả kiểm tra nghiệm duy nhất đối chiếu với bộ giải độc lập.                                                                                |
| `run_log.jsonl`, `environment.json`        | Chi tiết lần chạy, lỗi và môi trường thực nghiệm.                                                                                              |
| `summary.md`                               | Bảng tổng hợp theo màn và kích thước bàn cờ. Khi có Matplotlib, chương trình xuất thêm biểu đồ PNG. |

CSV lưu cả những lượt gặp lỗi hoặc vượt thời gian cho phép. Khi so sánh hai cấu hình, dùng cùng bộ dữ liệu. Cách tính từng chỉ số có trong [hướng dẫn benchmark](benchmark/README.md).

## Cấu trúc mã nguồn

| Đường dẫn                                                                  | Vai trò                                                                                                          |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `main.py`                                                                  | Đọc danh sách puzzle, khởi động server và mở trình duyệt.                                                        |
| `griductive/engine.py`                                                     | Giữ dữ liệu ẩn, cung cấp trạng thái công khai và kiểm tra phán đoán trước khi lật thẻ.                           |
| `griductive/models.py`, `griductive/regions.py`, `griductive/semantics.py` | Đọc dữ liệu màn chơi theo lược đồ `1.0.0`, xác định các ô thuộc vùng và đánh giá manh mối trên một phép gán đầy đủ. |
| `griductive/encoder.py`                                                    | Ánh xạ ô sang biến và tự động chuyển manh mối đã mở cùng trạng thái đã biết thành CNF.                           |
| `griductive/sat.py`                                                        | Cài DPLL với lan truyền đơn vị, chọn nhánh theo thứ tự cố định, quay lui và ghi số liệu cho mỗi truy vấn.        |
| `griductive/agent.py`                                                      | Kiểm tra hai giả thiết về nhân vật trên trạng thái công khai để tìm kết luận có thể chứng minh ở lượt tiếp theo. |
| `griductive/uniqueness.py`                                                 | Kiểm tra nghiệm duy nhất trên toàn bộ manh mối bằng mệnh đề chặn phép gán của các biến chính.                    |
| `griductive/gui/`                                                          | Phục vụ giao diện, điều phối phiên chơi và ghi nhật ký suy luận.                                                 |
| `puzzles/`, `benchmark/`                                                   | Dữ liệu màn chơi, ca kiểm thử, bộ giải đối chứng và chương trình thực nghiệm.                                    |

Bộ mã hóa xử lý sáu loại manh mối `FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST` và `AT_MOST`. Manh mối có thể áp dụng cho một hàng, một cột, các ô kề hoặc một danh sách ô chỉ định. Hai loại vùng mở rộng là `CORNERS` (ô góc) và `BOUNDARY` (ô viền). Nhóm ghi lược đồ dữ liệu và giao diện giữa các mô-đun trong `TEAM_CONVENTIONS.md`.
