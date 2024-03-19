CREATE TABLE users
(
    user_id     BIGINT PRIMARY KEY,
    usage_count INT DEFAULT 0,
    user_handle VARCHAR(255) NOT NULL
);

CREATE TABLE tasks
(
    task_id           SERIAL PRIMARY KEY,
    user_id           BIGINT REFERENCES users (user_id),
    first_photo_path  TEXT,
    second_photo_path TEXT,
    result_photo_path TEXT,
    status            TEXT DEFAULT 'pending'
);