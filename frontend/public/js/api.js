// API 기본 설정
const API_BASE = '';

// API 호출 헬퍼 함수
async function apiCall(url, options = {}) {
    try {
        const token = localStorage.getItem('authToken');
        const defaultHeaders = {
            'Content-Type': 'application/json',
        };
        
        if (token) {
            defaultHeaders['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await fetch(url, {
            ...options,
            headers: {
                ...defaultHeaders,
                ...options.headers
            }
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || data.error || 'API 호출에 실패했습니다');
        }
        
        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// User Service API
const userAPI = {
    // 회원가입
    async register(userData) {
        return await apiCall('/api/user/signup', {
            method: 'POST',
            body: JSON.stringify(userData)
        });
    },
    
    // 로그인
    async login(credentials) {
        const formData = new FormData();
        formData.append('username', credentials.username);
        formData.append('password', credentials.password);
        
        return await apiCall('/api/user/login', {
            method: 'POST',
            headers: {},
            body: formData
        });
    },
    
    // 사용자 정보 조회
    async getUser(userId) {
        return await apiCall(`/api/user/users/${userId}`);
    },
    
    // 사용자 유효성 검증
    async validateUser() {
        return await apiCall('/api/user/validate', {
            method: 'POST'
        });
    }
};

// Restaurant Service API
const restaurantAPI = {
    // 전체 메뉴 조회
    async getAllMenus() {
        return await apiCall('/api/restaurant/menus');
    },
    
    // 단일 메뉴 조회
    async getMenu(menuId) {
        return await apiCall(`/api/restaurant/menus/${menuId}`);
    },
    
    // 레스토랑 목록 조회
    async getRestaurants() {
        return await apiCall('/api/restaurant/restaurants');
    }
};

// Order Service API
const orderAPI = {
    // 주문 생성
    async createOrder(orderData) {
        return await apiCall('/api/order/orders', {
            method: 'POST',
            body: JSON.stringify(orderData)
        });
    },
    
    // 주문 조회
    async getOrder(orderId) {
        return await apiCall(`/api/order/orders/${orderId}`);
    },
    
    // 주문 취소
    async cancelOrder(orderId) {
        return await apiCall(`/api/order/orders/${orderId}/cancel`, {
            method: 'POST'
        });
    }
};

// 에러 처리 유틸리티
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    
    // 기존 alert 제거
    const existingAlert = document.querySelector('.alert');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    // 페이지 상단에 alert 추가
    const main = document.querySelector('.main');
    if (main) {
        main.insertBefore(alertDiv, main.firstChild);
        
        // 3초 후 자동 제거
        setTimeout(() => {
            alertDiv.remove();
        }, 3000);
    }
}

// 로딩 스피너 표시/숨기기
function showLoading(container) {
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
        </div>
    `;
}

function hideLoading() {
    const loading = document.querySelector('.loading');
    if (loading) {
        loading.remove();
    }
}

// 가격 포맷팅
function formatPrice(price) {
    return new Intl.NumberFormat('ko-KR').format(price) + '원';
}

// 날짜 포맷팅
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR');
} 