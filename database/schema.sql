CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    full_name TEXT,
    plan TEXT DEFAULT 'free',
    join_date DATE DEFAULT CURRENT_DATE,
    telegram_chat_id TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE links (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    platform TEXT DEFAULT 'generic',
    check_frequency TEXT DEFAULT 'daily',
    last_checked TIMESTAMP,
    last_status TEXT,
    last_response_time INTEGER,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE check_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    link_id UUID REFERENCES links(id) ON DELETE CASCADE,
    status TEXT,
    response_time INTEGER,
    error_message TEXT,
    layer_used TEXT,
    checked_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE alerts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    link_id UUID REFERENCES links(id) ON DELETE CASCADE,
    alert_type TEXT,
    message TEXT,
    sent_via TEXT,
    sent_at TIMESTAMP DEFAULT NOW()
);
