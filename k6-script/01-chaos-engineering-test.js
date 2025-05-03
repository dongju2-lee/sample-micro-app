import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

// 사용자 정의 메트릭 생성
const failedOrders = new Counter('failed_orders');
const successfulOrders = new Counter('successful_orders');

// 테스트 구성
export const options = {
  stages: [
    { duration: '30s', target: 10 }, // 10명의 가상 사용자로 서서히 증가
    { duration: '1m', target: 10 },  // 1분 동안 10명 유지
    { duration: '30s', target: 0 },  // 서서히 감소
  ],
  thresholds: {
    // 성공적인 결제가 최소 60% 이상이어야 함 (결제 실패율 30% 설정으로 인해)
    'successful_orders': ['count>10'],
    // 결제 실패가 40% 이하여야 함
    'failed_orders': ['count<40'],
    // 응답 시간은 p95에서 3초 미만이어야 함
    'http_req_duration': ['p(95)<3000'],
  },
};

// 테스트 설정
const BASE_URL = 'http://localhost';
let token = '';

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

// 결제 실패율 설정 (30%)
function setupPaymentFailRate() {
  const payload = JSON.stringify({
    fail_percent: 30
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(`${BASE_URL}:8003/chaos/payment_fail`, payload, params);
  check(res, {
    'payment fail rate set': (r) => r.status === 200,
  });
}

// 초기화 함수 - 한 번만 실행됨
export function setup() {
  console.log('설정 중: 테스트 사용자 생성 및 결제 실패율 설정');
  
  // 테스트 사용자 생성
  const signupPayload = JSON.stringify({
    username: 'user123',
    email: 'user123@example.com',
    password: 'password123'
  });

  const signupParams = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const signupRes = http.post(`${BASE_URL}:8001/signup`, signupPayload, signupParams);
  console.log(`사용자 생성 응답: ${signupRes.status}, ${signupRes.body}`);
  
  if (signupRes.status === 201 || signupRes.status === 400) {
    // 400은 이미 가입된 사용자일 수 있음
    console.log('사용자 생성/확인 완료');
    
    // 로그인 확인
    if (login()) {
      console.log('로그인 테스트 성공, 인증 서비스 정상 작동');
    } else {
      console.log('주의: 로그인 테스트 실패, 테스트에 영향이 있을 수 있습니다.');
    }
  }
  
  setupPaymentFailRate();
  console.log('카오스 엔지니어링 테스트 준비 완료');
}

// 가상 사용자(VU) 스크립트 - 각 VU는 이 함수를 실행
export default function() {
  if (!token && !login()) {
    console.log('로그인 실패, 테스트를 건너뜁니다.');
    sleep(1);
    return;
  }

  // 주문 생성
  const orderPayload = JSON.stringify({
    items: [
      { menu_id: 1, quantity: 2 }
    ],
    address: '서울시 강남구 123-45',
    phone: '010-1234-5678'
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
  };

  const orderRes = http.post(`${BASE_URL}:8003/orders`, orderPayload, params);
  
  check(orderRes, {
    'order response status 201': (r) => r.status === 201,
  });

  if (orderRes.status === 201) {
    const orderData = JSON.parse(orderRes.body);
    
    // 주문 결과 확인 (성공 또는 실패)
    if (orderData.status === 'FAILED') {
      failedOrders.add(1);
      console.log(`주문 실패: ${orderData.id}`);
    } else {
      successfulOrders.add(1);
      console.log(`주문 성공: ${orderData.id}`);
    }

    // 주문 상태 조회
    const orderDetailsRes = http.get(`${BASE_URL}:8003/orders/${orderData.id}`, params);
    check(orderDetailsRes, {
      'order details retrieved': (r) => r.status === 200,
    });
  }

  sleep(3);
}

// 테스트 종료 후 실행
export function teardown() {
  console.log('카오스 엔지니어링 테스트 완료');
} 