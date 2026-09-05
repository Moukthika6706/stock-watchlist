-- StockSense schema (MySQL 8). Idempotent: drops and recreates every table.
-- Run via `venv\Scripts\python.exe reset_db.py --yes`, which also creates the
-- database named in .env if it does not exist yet.

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS price_alerts;
DROP TABLE IF EXISTS last_seen;
DROP TABLE IF EXISTS price_snapshots;
DROP TABLE IF EXISTS watchlist;
DROP TABLE IF EXISTS stocks;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE users (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE stocks (
  id INT NOT NULL AUTO_INCREMENT,
  symbol VARCHAR(20) NOT NULL,
  company_name VARCHAR(150) NOT NULL,
  current_price DECIMAL(12,2) DEFAULT NULL,
  market VARCHAR(50) DEFAULT NULL,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- who is watching what
CREATE TABLE watchlist (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  stock_id INT NOT NULL,
  added_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY user_id (user_id, stock_id),
  KEY stock_id (stock_id),
  CONSTRAINT watchlist_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT watchlist_ibfk_2 FOREIGN KEY (stock_id) REFERENCES stocks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- shared price history: many rows per stock, written by the poller / seed script
CREATE TABLE price_snapshots (
  id INT NOT NULL AUTO_INCREMENT,
  stock_id INT NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  percent_change DECIMAL(8,4) DEFAULT NULL,
  volume BIGINT DEFAULT NULL,
  average_volume BIGINT DEFAULT NULL,
  day_high DECIMAL(12,2) DEFAULT NULL,
  day_low DECIMAL(12,2) DEFAULT NULL,
  week52_high DECIMAL(12,2) DEFAULT NULL,
  week52_low DECIMAL(12,2) DEFAULT NULL,
  is_market_open TINYINT(1) DEFAULT NULL,
  captured_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY stock_id (stock_id),
  CONSTRAINT price_snapshots_ibfk_1 FOREIGN KEY (stock_id) REFERENCES stocks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- what each user saw last time: one row per user+stock, upserted on every GET /watchlist
CREATE TABLE last_seen (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  stock_id INT NOT NULL,
  last_seen_price DECIMAL(12,2) DEFAULT NULL,
  last_seen_volume BIGINT DEFAULT NULL,
  last_seen_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY user_id (user_id, stock_id),
  KEY stock_id (stock_id),
  CONSTRAINT last_seen_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT last_seen_ibfk_2 FOREIGN KEY (stock_id) REFERENCES stocks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- passive in-app thresholds only, no delivery
CREATE TABLE price_alerts (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  stock_id INT NOT NULL,
  target_price DECIMAL(12,2) NOT NULL,
  alert_type ENUM('ABOVE','BELOW') NOT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY user_id (user_id),
  KEY stock_id (stock_id),
  CONSTRAINT price_alerts_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT price_alerts_ibfk_2 FOREIGN KEY (stock_id) REFERENCES stocks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
