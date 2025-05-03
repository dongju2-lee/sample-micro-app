import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

// 사용자 정의 메트릭 생성
const successfulOrders = new Counter('successful_orders');
const cancelledOrders = new Counter('cancelled_orders');
const reorders = new Counter('reorders');

// 테스트 구성
export const options = {
  stages: [
    { duration: '20s', target: 10 },  // 10명의 가상 사용자로 증가
    { duration: '1m', target: 10 },   // 1분 동안 유지
    { duration: '20s', target: 0 },   // 서서히 감소
  ],
  thresholds: {
    // 취소된 주문 수와 재주문 수가 거의 같아야 함
    'reorders': ['count>5'],
    'cancelled_orders': ['count>5'],
    // 응답 시간
    'http_req_duration': ['p(95)<3000'],
  },
};

// 테스트 설정
const BASE_URL = 'http://localhost';
let token = '';
let orderId = null;

// 로그인하여 토큰 얻기
function login() {
  // OAuth2 형식으로 Form 데이터 전송
  const formData = {
    username: 'user123',
    password: 'password123'
  };

  const params = {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  };

  const loginRes = http.post(`${BASE_URL}:8001/login`, formData, params);
  check(loginRes, {
    'login successful': (r) => r.status === 200,
  });

  if (loginRes.status === 200) {
    const body = JSON.parse(loginRes.body);
    token = body.access_token;
    return true;
  }
  console.log(`로그인 실패: 상태 코드 ${loginRes.status}, 응답: ${loginRes.body}`);
  return false;
}

// 초기화 함수 - 테스트 사용자 생성
export function setup() {
  console.log('취소-재주문 테스트 준비 중');
  
  // 테스트 사용자 생성
  const signupPayload = JSON.stringify({
    username: 'user123',
    email: 'user123@example.com',
    password: 'password123'
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const signupRes = http.post(`${BASE_URL}:8001/signup`, signupPayload, params);
  if (signupRes.status === 201 || signupRes.status === 400) {
    // 400은 이미 가입된 사용자일 수 있음
    console.log('사용자 생성/확인 완료');
  }
  
  console.log('취소-재주문 테스트 준비 완료');
}

// 가상 사용자(VU) 스크립트 - 각 VU는 이 함수를 실행
export default function() {
  if (!token && !login()) {
    console.log('로그인 실패, 테스트를 건너뜁니다.');
    sleep(1);
    return;
  }
  
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
  };

  // 1. 주문 생성
  const orderPayload = JSON.stringify({
    items: [
      { menu_id: 1, quantity: 1 }
    ],
    address: '서울시 강남구 123-45',
    phone: '010-1234-5678'
  });

  const orderRes = http.post(`${BASE_URL}:8003/orders`, orderPayload, params);
  
  check(orderRes, {
    'order created successfully': (r) => r.status === 201,
  });

  if (orderRes.status === 201) {
    const orderData = JSON.parse(orderRes.body);
    orderId = orderData.id;
    successfulOrders.add(1);
    
    console.log(`주문 생성 완료: ${orderId}`);
    sleep(1); // 주문 생성 후 약간의 지연
    
    // 2. 주문 취소
    const cancelRes = http.post(`${BASE_URL}:8003/orders/${orderId}/cancel`, {}, params);
    
    check(cancelRes, {
      'order cancelled successfully': (r) => r.status === 200,
    });
    
    if (cancelRes.status === 200) {
      cancelledOrders.add(1);
      console.log(`주문 취소 완료: ${orderId}`);
      
      sleep(1); // 취소 후 약간의 지연
      
      // 3. 동일한 메뉴로 재주문
      const reorderRes = http.post(`${BASE_URL}:8003/orders`, orderPayload, params);
      
      check(reorderRes, {
        'reorder successful': (r) => r.status === 201,
      });
      
      if (reorderRes.status === 201) {
        const reorderData = JSON.parse(reorderRes.body);
        reorders.add(1);
        console.log(`재주문 완료: ${reorderData.id}`);
        
        // 4. 새 주문 상태 확인
        const orderStatusRes = http.get(`${BASE_URL}:8003/orders/${reorderData.id}`, params);
        
        check(orderStatusRes, {
          'reorder status check': (r) => r.status === 200,
        });
      }
    }
  }
  
  // 각 VU 실행 사이에 지연
  sleep(3);
}

// 테스트 종료 후 실행
export function teardown() {
  console.log('취소-재주문 테스트 완료');
} 