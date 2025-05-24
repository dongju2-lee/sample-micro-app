// 장바구니 관리
class CartManager {
    constructor() {
        this.cart = JSON.parse(localStorage.getItem('cart') || '[]');
        this.init();
    }
    
    init() {
        this.updateCartUI();
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // 장바구니 토글 버튼
        document.addEventListener('click', (e) => {
            if (e.target.id === 'cartToggleBtn') {
                this.toggleCart();
            }
            
            if (e.target.classList.contains('add-to-cart')) {
                const menuId = parseInt(e.target.dataset.menuId);
                this.addToCart(menuId);
            }
            
            if (e.target.classList.contains('remove-from-cart')) {
                const menuId = parseInt(e.target.dataset.menuId);
                this.removeFromCart(menuId);
            }
            
            if (e.target.id === 'checkoutBtn') {
                this.checkout();
            }
        });
    }
    
    addToCart(menuId) {
        const existingItem = this.cart.find(item => item.menu_id === menuId);
        
        if (existingItem) {
            existingItem.quantity += 1;
        } else {
            this.cart.push({
                menu_id: menuId,
                quantity: 1
            });
        }
        
        this.saveCart();
        this.updateCartUI();
        showAlert('장바구니에 추가되었습니다!', 'success');
    }
    
    removeFromCart(menuId) {
        const itemIndex = this.cart.findIndex(item => item.menu_id === menuId);
        
        if (itemIndex > -1) {
            const item = this.cart[itemIndex];
            
            if (item.quantity > 1) {
                item.quantity -= 1;
            } else {
                this.cart.splice(itemIndex, 1);
            }
            
            this.saveCart();
            this.updateCartUI();
        }
    }
    
    saveCart() {
        localStorage.setItem('cart', JSON.stringify(this.cart));
    }
    
    async updateCartUI() {
        const cartCount = document.getElementById('cartCount');
        const cartItems = document.getElementById('cartItems');
        const cartTotal = document.getElementById('cartTotal');
        
        const totalItems = this.cart.reduce((sum, item) => sum + item.quantity, 0);
        
        if (cartCount) {
            cartCount.textContent = totalItems;
        }
        
        if (cartItems && cartTotal) {
            if (this.cart.length === 0) {
                cartItems.innerHTML = '<p>장바구니가 비어있습니다.</p>';
                cartTotal.textContent = '총 금액: 0원';
                return;
            }
            
            try {
                let total = 0;
                let itemsHTML = '';
                
                for (const cartItem of this.cart) {
                    const menu = await restaurantAPI.getMenu(cartItem.menu_id);
                    const itemTotal = menu.price * cartItem.quantity;
                    total += itemTotal;
                    
                    itemsHTML += `
                        <div class="cart-item">
                            <div>
                                <h4>${menu.name}</h4>
                                <p>${formatPrice(menu.price)} × ${cartItem.quantity}</p>
                            </div>
                            <div>
                                <button class="btn btn-small btn-secondary remove-from-cart" 
                                        data-menu-id="${cartItem.menu_id}">-</button>
                                <span style="margin: 0 10px;">${cartItem.quantity}</span>
                                <button class="btn btn-small btn-secondary add-to-cart" 
                                        data-menu-id="${cartItem.menu_id}">+</button>
                            </div>
                        </div>
                    `;
                }
                
                cartItems.innerHTML = itemsHTML;
                cartTotal.textContent = `총 금액: ${formatPrice(total)}`;
                
            } catch (error) {
                console.error('Error updating cart UI:', error);
            }
        }
    }
    
    toggleCart() {
        const cart = document.getElementById('cart');
        if (cart) {
            cart.classList.toggle('open');
        }
    }
    
    async checkout() {
        if (!authManager.requireAuth()) {
            return;
        }
        
        if (this.cart.length === 0) {
            showAlert('장바구니가 비어있습니다.', 'error');
            return;
        }
        
        // 주문 페이지로 이동
        window.location.href = '/order.html';
    }
    
    clearCart() {
        this.cart = [];
        this.saveCart();
        this.updateCartUI();
    }
}

// 메뉴 관리
class MenuManager {
    constructor() {
        this.menus = [];
        this.init();
    }
    
    async init() {
        await this.loadMenus();
        this.renderMenus();
    }
    
    async loadMenus() {
        try {
            const container = document.getElementById('menuContainer');
            if (container) {
                showLoading(container);
                this.menus = await restaurantAPI.getAllMenus();
            }
        } catch (error) {
            showAlert('메뉴를 불러오는데 실패했습니다.', 'error');
            console.error('Error loading menus:', error);
        }
    }
    
    renderMenus() {
        const container = document.getElementById('menuContainer');
        if (!container) return;
        
        if (this.menus.length === 0) {
            container.innerHTML = '<p>메뉴가 없습니다.</p>';
            return;
        }
        
        const menuHTML = this.menus.map(menu => `
            <div class="menu-item">
                <div class="menu-item-image">
                    🍽️
                </div>
                <div class="menu-item-content">
                    <h3>${menu.name}</h3>
                    <p>${menu.description || '맛있는 음식입니다!'}</p>
                    <div class="menu-item-footer">
                        <div>
                            <div class="price">${formatPrice(menu.price)}</div>
                            <div class="inventory">재고: ${menu.inventory}개</div>
                        </div>
                        <button class="btn btn-primary btn-small add-to-cart" 
                                data-menu-id="${menu.id}"
                                ${!menu.is_available ? 'disabled' : ''}>
                            ${menu.is_available ? '담기' : '품절'}
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
        
        container.innerHTML = `<div class="menu-grid">${menuHTML}</div>`;
    }
}

// 주문 관리
class OrderManager {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        
        // 주문 페이지인 경우
        if (window.location.pathname.includes('order.html')) {
            this.renderOrderForm();
        }
        
        // 주문 내역 페이지인 경우
        if (window.location.pathname.includes('orders.html')) {
            this.loadOrders();
        }
    }
    
    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('cancel-order')) {
                const orderId = parseInt(e.target.dataset.orderId);
                this.cancelOrder(orderId);
            }
        });
        
        const orderForm = document.getElementById('orderForm');
        if (orderForm) {
            orderForm.addEventListener('submit', (e) => this.handleOrder(e));
        }
    }
    
    async renderOrderForm() {
        if (!authManager.requireAuth()) {
            return;
        }
        
        const cart = JSON.parse(localStorage.getItem('cart') || '[]');
        if (cart.length === 0) {
            showAlert('장바구니가 비어있습니다.', 'error');
            window.location.href = '/';
            return;
        }
        
        const container = document.getElementById('orderSummary');
        if (!container) return;
        
        try {
            let total = 0;
            let itemsHTML = '';
            
            for (const cartItem of cart) {
                const menu = await restaurantAPI.getMenu(cartItem.menu_id);
                const itemTotal = menu.price * cartItem.quantity;
                total += itemTotal;
                
                itemsHTML += `
                    <div class="order-item">
                        <h4>${menu.name}</h4>
                        <p>${formatPrice(menu.price)} × ${cartItem.quantity} = ${formatPrice(itemTotal)}</p>
                    </div>
                `;
            }
            
            container.innerHTML = `
                <div class="card">
                    <h3>주문 내역</h3>
                    ${itemsHTML}
                    <hr>
                    <div class="order-total">
                        <strong>총 금액: ${formatPrice(total)}</strong>
                    </div>
                </div>
            `;
            
        } catch (error) {
            showAlert('주문 정보를 불러오는데 실패했습니다.', 'error');
            console.error('Error rendering order form:', error);
        }
    }
    
    async handleOrder(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const cart = JSON.parse(localStorage.getItem('cart') || '[]');
        
        const orderData = {
            items: cart,
            address: formData.get('address'),
            phone: formData.get('phone')
        };
        
        try {
            const order = await orderAPI.createOrder(orderData);
            showAlert('주문이 성공적으로 생성되었습니다!', 'success');
            
            // 장바구니 비우기
            cartManager.clearCart();
            
            // 주문 내역 페이지로 이동
            setTimeout(() => {
                window.location.href = '/orders.html';
            }, 1000);
            
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }
    
    async loadOrders() {
        if (!authManager.requireAuth()) {
            return;
        }
        
        // 실제로는 사용자별 주문 내역을 가져와야 하지만,
        // 현재 API에서는 지원하지 않으므로 로컬 스토리지에서 가져오거나
        // 간단한 데모용 데이터를 표시합니다.
        
        const container = document.getElementById('ordersContainer');
        if (!container) return;
        
        container.innerHTML = `
            <div class="card">
                <h3>주문 내역</h3>
                <p>주문 내역이 없습니다.</p>
                <p class="text-muted">실제 애플리케이션에서는 사용자별 주문 내역을 조회할 수 있는 API가 필요합니다.</p>
            </div>
        `;
    }
    
    async cancelOrder(orderId) {
        try {
            await orderAPI.cancelOrder(orderId);
            showAlert('주문이 취소되었습니다.', 'success');
            this.loadOrders();
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }
}

// 자동 테스트 관리
class AutoTestManager {
    constructor() {
        this.isRunning = false;
        this.testInterval = null;
        this.testCounter = 0;
        this.maxTests = 20; // 최대 테스트 횟수
        this.testAccounts = [
            { username: 'testuser1', email: 'test1@example.com', password: 'test123' },
            { username: 'testuser2', email: 'test2@example.com', password: 'test123' },
            { username: 'testuser3', email: 'test3@example.com', password: 'test123' }
        ];
        this.currentAccount = null;
        this.init();
    }
    
    init() {
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (e.target.id === 'autoTestBtn') {
                this.toggleAutoTest();
            }
        });
    }
    
    toggleAutoTest() {
        if (this.isRunning) {
            this.stopAutoTest();
        } else {
            this.startAutoTest();
        }
    }
    
    startAutoTest() {
        this.isRunning = true;
        this.testCounter = 0;
        this.updateButtonText('🛑 테스트 중지');
        
        showAlert('자동 테스트가 시작되었습니다! 랜덤 사용자 행동을 시뮬레이션합니다.', 'info');
        
        // 3초마다 랜덤 액션 실행
        this.testInterval = setInterval(() => {
            this.performRandomAction();
            this.testCounter++;
            
            if (this.testCounter >= this.maxTests) {
                this.stopAutoTest();
            }
        }, 3000);
    }
    
    stopAutoTest() {
        this.isRunning = false;
        if (this.testInterval) {
            clearInterval(this.testInterval);
            this.testInterval = null;
        }
        this.updateButtonText('🤖 자동 테스트');
        showAlert('자동 테스트가 중지되었습니다.', 'info');
    }
    
    updateButtonText(text) {
        const btn = document.getElementById('autoTestBtn');
        if (btn) {
            btn.textContent = text;
            if (this.isRunning) {
                btn.classList.add('running');
            } else {
                btn.classList.remove('running');
            }
        }
    }
    
    async performRandomAction() {
        const actions = [
            'createTestAccount',
            'loginTestAccount',
            'addRandomItemsToCart',
            'toggleCart',
            'removeRandomItemFromCart',
            'clearCart',
            'navigateToOrderPage',
            'navigateToOrderHistory',
            'navigateHome',
            'createRandomOrder',
            'logout'
        ];
        
        // 로그인 상태에 따라 사용 가능한 액션 필터링
        const availableActions = actions.filter(action => {
            if (['createTestAccount', 'loginTestAccount'].includes(action)) {
                return !authManager.isLoggedIn();
            }
            if (['addRandomItemsToCart', 'navigateToOrderPage', 'createRandomOrder', 'logout'].includes(action)) {
                return authManager.isLoggedIn();
            }
            return true;
        });
        
        const randomAction = availableActions[Math.floor(Math.random() * availableActions.length)];
        
        try {
            await this[randomAction]();
        } catch (error) {
            console.log('Auto test action failed:', error.message);
        }
    }
    
    async createTestAccount() {
        const account = this.testAccounts[Math.floor(Math.random() * this.testAccounts.length)];
        this.currentAccount = account;
        
        showAlert(`테스트 계정 생성 시도: ${account.username}`, 'info');
        
        try {
            await userAPI.register(account);
            showAlert('테스트 계정이 생성되었습니다!', 'success');
        } catch (error) {
            // 이미 존재하는 계정일 수 있으므로 에러 무시
            console.log('Account might already exist:', error.message);
        }
    }
    
    async loginTestAccount() {
        if (!this.currentAccount) {
            this.currentAccount = this.testAccounts[Math.floor(Math.random() * this.testAccounts.length)];
        }
        
        showAlert(`테스트 계정 로그인: ${this.currentAccount.username}`, 'info');
        
        try {
            const response = await userAPI.login({
                username: this.currentAccount.username,
                password: this.currentAccount.password
            });
            
            authManager.token = response.access_token;
            localStorage.setItem('authToken', authManager.token);
            await authManager.validateToken();
            
            showAlert('자동 로그인 성공!', 'success');
        } catch (error) {
            // 계정이 없으면 생성 후 로그인 시도
            await this.createTestAccount();
            setTimeout(() => this.loginTestAccount(), 1000);
        }
    }
    
    async addRandomItemsToCart() {
        if (!menuManager || !menuManager.menus.length) {
            return;
        }
        
        const availableMenus = menuManager.menus.filter(menu => menu.is_available);
        if (availableMenus.length === 0) {
            return;
        }
        
        const randomCount = Math.floor(Math.random() * 3) + 1; // 1-3개 아이템
        
        for (let i = 0; i < randomCount; i++) {
            const randomMenu = availableMenus[Math.floor(Math.random() * availableMenus.length)];
            cartManager.addToCart(randomMenu.id);
            
            // 약간의 지연
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        
        showAlert(`${randomCount}개의 랜덤 메뉴를 장바구니에 추가했습니다!`, 'success');
    }
    
    toggleCart() {
        cartManager.toggleCart();
        showAlert('장바구니를 토글했습니다.', 'info');
    }
    
    removeRandomItemFromCart() {
        if (cartManager.cart.length === 0) {
            return;
        }
        
        const randomItem = cartManager.cart[Math.floor(Math.random() * cartManager.cart.length)];
        cartManager.removeFromCart(randomItem.menu_id);
        showAlert('랜덤 아이템을 장바구니에서 제거했습니다.', 'info');
    }
    
    clearCart() {
        if (cartManager.cart.length > 0) {
            cartManager.clearCart();
            showAlert('장바구니를 비웠습니다.', 'info');
        }
    }
    
    navigateToOrderPage() {
        if (cartManager.cart.length > 0) {
            showAlert('주문 페이지로 이동합니다.', 'info');
            setTimeout(() => {
                window.location.href = '/order.html';
            }, 1000);
        }
    }
    
    navigateToOrderHistory() {
        showAlert('주문 내역 페이지로 이동합니다.', 'info');
        setTimeout(() => {
            window.location.href = '/orders.html';
        }, 1000);
    }
    
    navigateHome() {
        if (window.location.pathname !== '/' && !window.location.pathname.includes('index.html')) {
            showAlert('홈페이지로 이동합니다.', 'info');
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        }
    }
    
    async createRandomOrder() {
        // 장바구니가 비어있으면 먼저 아이템 추가
        if (cartManager.cart.length === 0) {
            await this.addRandomItemsToCart();
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        
        if (cartManager.cart.length === 0) {
            return; // 메뉴가 없거나 추가 실패
        }
        
        const addresses = [
            '서울시 강남구 테헤란로 123',
            '서울시 마포구 홍대입구역 456',
            '서울시 종로구 종로3가 789',
            '서울시 송파구 잠실동 101',
            '서울시 영등포구 여의도동 202'
        ];
        
        const phones = [
            '010-1234-5678',
            '010-2345-6789',
            '010-3456-7890',
            '010-4567-8901',
            '010-5678-9012'
        ];
        
        const orderData = {
            items: cartManager.cart,
            address: addresses[Math.floor(Math.random() * addresses.length)],
            phone: phones[Math.floor(Math.random() * phones.length)]
        };
        
        try {
            showAlert('랜덤 주문을 생성합니다...', 'info');
            const order = await orderAPI.createOrder(orderData);
            showAlert(`주문이 성공적으로 생성되었습니다! 주문 ID: ${order.id}`, 'success');
            
            // 장바구니 비우기
            cartManager.clearCart();
            
        } catch (error) {
            showAlert(`주문 생성 실패: ${error.message}`, 'error');
        }
    }
    
    logout() {
        if (authManager.isLoggedIn()) {
            showAlert('자동 로그아웃합니다.', 'info');
            authManager.logout();
        }
    }
}

// 전역 인스턴스들
let cartManager;
let menuManager;
let orderManager;
let autoTestManager;

// DOM 로드 완료 후 초기화
document.addEventListener('DOMContentLoaded', () => {
    cartManager = new CartManager();
    autoTestManager = new AutoTestManager();
    
    // 홈페이지인 경우 메뉴 로드
    if (window.location.pathname === '/' || window.location.pathname.includes('index.html')) {
        menuManager = new MenuManager();
    }
    
    // 주문 관련 페이지인 경우
    if (window.location.pathname.includes('order') || window.location.pathname.includes('orders')) {
        orderManager = new OrderManager();
    }
}); 