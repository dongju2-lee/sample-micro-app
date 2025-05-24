// 인증 상태 관리
class AuthManager {
    constructor() {
        this.token = localStorage.getItem('authToken');
        this.user = JSON.parse(localStorage.getItem('user') || 'null');
        this.init();
    }
    
    init() {
        this.updateUI();
        this.setupEventListeners();
        
        // 토큰이 있으면 사용자 정보 검증
        if (this.token) {
            this.validateToken();
        }
    }
    
    async validateToken() {
        try {
            const userData = await userAPI.validateUser();
            this.user = userData;
            localStorage.setItem('user', JSON.stringify(userData));
            this.updateUI();
        } catch (error) {
            console.error('Token validation failed:', error);
            this.logout();
        }
    }
    
    setupEventListeners() {
        // 로그인 폼
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }
        
        // 회원가입 폼
        const registerForm = document.getElementById('registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
        }
        
        // 로그아웃 버튼
        document.addEventListener('click', (e) => {
            if (e.target.id === 'logoutBtn') {
                this.logout();
            }
        });
    }
    
    async handleLogin(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const credentials = {
            username: formData.get('username'),
            password: formData.get('password')
        };
        
        try {
            const response = await userAPI.login(credentials);
            this.token = response.access_token;
            localStorage.setItem('authToken', this.token);
            
            // 사용자 정보 가져오기
            await this.validateToken();
            
            showAlert('로그인에 성공했습니다!', 'success');
            
            // 홈페이지로 리다이렉트
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
            
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }
    
    async handleRegister(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const userData = {
            username: formData.get('username'),
            email: formData.get('email'),
            password: formData.get('password')
        };
        
        const confirmPassword = formData.get('confirmPassword');
        
        // 비밀번호 확인
        if (userData.password !== confirmPassword) {
            showAlert('비밀번호가 일치하지 않습니다.', 'error');
            return;
        }
        
        try {
            await userAPI.register(userData);
            showAlert('회원가입에 성공했습니다! 로그인해주세요.', 'success');
            
            // 로그인 페이지로 리다이렉트
            setTimeout(() => {
                window.location.href = '/login.html';
            }, 1000);
            
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }
    
    logout() {
        this.token = null;
        this.user = null;
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        localStorage.removeItem('cart');
        this.updateUI();
        
        showAlert('로그아웃되었습니다.', 'info');
        
        // 홈페이지로 리다이렉트
        setTimeout(() => {
            window.location.href = '/';
        }, 1000);
    }
    
    updateUI() {
        const authSection = document.querySelector('.auth-section');
        if (!authSection) return;
        
        if (this.isLoggedIn()) {
            authSection.innerHTML = `
                <span class="user-info">안녕하세요, ${this.user.username}님!</span>
                <a href="/orders.html" class="btn btn-secondary btn-small">주문내역</a>
                <button id="logoutBtn" class="btn btn-danger btn-small">로그아웃</button>
            `;
        } else {
            authSection.innerHTML = `
                <a href="/login.html" class="btn btn-secondary">로그인</a>
                <a href="/register.html" class="btn btn-primary">회원가입</a>
            `;
        }
    }
    
    isLoggedIn() {
        return !!(this.token && this.user);
    }
    
    requireAuth() {
        if (!this.isLoggedIn()) {
            showAlert('로그인이 필요합니다.', 'error');
            setTimeout(() => {
                window.location.href = '/login.html';
            }, 1000);
            return false;
        }
        return true;
    }
}

// 전역 인스턴스 생성
const authManager = new AuthManager(); 