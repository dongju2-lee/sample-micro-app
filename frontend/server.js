const express = require('express');
const cors = require('cors');
const axios = require('axios');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// 환경변수에서 마이크로서비스 URL 가져오기
const USER_SERVICE_URL = process.env.USER_SERVICE_URL || 'http://localhost:8001';
const RESTAURANT_SERVICE_URL = process.env.RESTAURANT_SERVICE_URL || 'http://localhost:8002';
const ORDER_SERVICE_URL = process.env.ORDER_SERVICE_URL || 'http://localhost:8003';

// 미들웨어 설정
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// API 프록시 라우트들
// User Service 프록시
app.all('/api/user/*', async (req, res) => {
    try {
        const apiPath = req.path.replace('/api/user', '');
        const url = `${USER_SERVICE_URL}${apiPath}`;
        
        const config = {
            method: req.method,
            url: url,
            headers: { ...req.headers },
            data: req.body,
            params: req.query
        };
        
        // host 헤더 제거 (프록시 시 문제 발생 가능)
        delete config.headers.host;
        
        const response = await axios(config);
        res.status(response.status).json(response.data);
    } catch (error) {
        console.error('User Service API Error:', error.message);
        if (error.response) {
            res.status(error.response.status).json(error.response.data);
        } else {
            res.status(500).json({ error: 'Internal Server Error' });
        }
    }
});

// Restaurant Service 프록시
app.all('/api/restaurant/*', async (req, res) => {
    try {
        const apiPath = req.path.replace('/api/restaurant', '');
        const url = `${RESTAURANT_SERVICE_URL}${apiPath}`;
        
        const config = {
            method: req.method,
            url: url,
            headers: { ...req.headers },
            data: req.body,
            params: req.query
        };
        
        delete config.headers.host;
        
        const response = await axios(config);
        res.status(response.status).json(response.data);
    } catch (error) {
        console.error('Restaurant Service API Error:', error.message);
        if (error.response) {
            res.status(error.response.status).json(error.response.data);
        } else {
            res.status(500).json({ error: 'Internal Server Error' });
        }
    }
});

// Order Service 프록시
app.all('/api/order/*', async (req, res) => {
    try {
        const apiPath = req.path.replace('/api/order', '');
        const url = `${ORDER_SERVICE_URL}${apiPath}`;
        
        const config = {
            method: req.method,
            url: url,
            headers: { ...req.headers },
            data: req.body,
            params: req.query
        };
        
        delete config.headers.host;
        
        const response = await axios(config);
        res.status(response.status).json(response.data);
    } catch (error) {
        console.error('Order Service API Error:', error.message);
        if (error.response) {
            res.status(error.response.status).json(error.response.data);
        } else {
            res.status(500).json({ error: 'Internal Server Error' });
        }
    }
});

// 헬스체크 엔드포인트
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy',
        service: 'frontend',
        timestamp: new Date().toISOString(),
        uptime: process.uptime()
    });
});

// SPA를 위한 catch-all 라우트
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
    console.log(`Frontend server running on port ${PORT}`);
    console.log(`User Service URL: ${USER_SERVICE_URL}`);
    console.log(`Restaurant Service URL: ${RESTAURANT_SERVICE_URL}`);
    console.log(`Order Service URL: ${ORDER_SERVICE_URL}`);
}); 