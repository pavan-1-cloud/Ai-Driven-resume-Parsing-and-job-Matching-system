-- CREATE TABLE users (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     email VARCHAR(255) NOT NULL UNIQUE,
--     password VARCHAR(255) NOT NULL
-- );

-- ALTER TABLE users
-- ADD COLUMN type ENUM('admin', 'user') NOT NULL DEFAULT 'user';


select * from users;

-- ALTER TABLE users
-- ADD COLUMN last_name VARCHAR(255) AFTER name,
-- ADD COLUMN phone VARCHAR(20) AFTER email,
-- ADD COLUMN resume_file VARCHAR(255) AFTER password;



-- INSERT INTO users (name, email, password, type)
-- VALUES (
--   'Admin',
--   'admin@gmail.com',
--   'scrypt:32768:8:1$qazYCY6RiuNqo1C2$2631c483b4927e612a251d4d59e2dec56889ba25265713d919994a23efab5155275380f6902443d08cd77d6a753c28cfdca8d4824098563626bd5b947542860b',
--   'admin'
-- );