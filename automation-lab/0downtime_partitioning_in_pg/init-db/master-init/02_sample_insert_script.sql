-- Insert 10 sample rows using generate_series and random values
INSERT INTO orders (product_name, quantity, order_date)
SELECT
    'Product ' || chr(65 + (i % 26)) || chr(65 + ((i + 1) % 26)),  -- Random product name (e.g., Product AB, Product BC, etc.)
    (i * 5) % 100 + 1,  -- Random quantity (1 to 100)
    CURRENT_DATE - (i * 10)  -- Random order date (every 10th day back from today)
FROM generate_series(1, 10) AS s(i);
