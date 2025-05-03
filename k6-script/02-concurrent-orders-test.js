import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter } from 'k6/metrics';

// 사용자 정의 메트릭 생성
const successfulOrders = new Counter('successful_orders');
const failedOrders = new Counter('failed_orders');

// 테스트 구성
export const options = {
  scenarios: {
    // 동시 접속 시나리오: 짧은 시간에 많은 동시 주문 생성
    concurrent_orders: {
      executor: 'ramping-arrival-rate', // 도착 속도 기반 부하 모델
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 100,
      stages: [
        { duration: '10s', target: 10 },  // 초당 1개에서 10개로 증가
        { duration: '30s', target: 30 },  // 초당 30개 주문으로 증가
        { duration: '1m', target: 30 },   // 1분 동안 초당 30개 유지
        { duration: '20s', target: 0 },   // 서서히 감소
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<3000'], // 95%의 요청이 3초 이내에 완료되어야 함
    http_req_failed: ['rate<0.1'],     // 실패율 10% 미만
    'successful_orders': ['count>50'],  // 최소 50개 주문 성공
  },
};

// 생성할 사용자 정보
const users = new SharedArray('users', function() {
  return Array(10).fill(0).map((_, i) => ({
    username: `testuser${i}`,
    password: `password${i}`,
    token: null
  }));
});

// 테스트 설정
const BASE_URL = 'http://localhost';
let token = '';

// 로그인하여 토큰 얻기
function login(user) {
  // OAuth2 형식으로 Form 데이터 전송
  const formData = {
    username: user.username,
    password: user.password
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
  console.log(`로그인 실패: ${user.username}, 상태: ${loginRes.status}, 응답: ${loginRes.body}`);
  return false;
}

// 초기화 - 사용자 회원가입 진행
export function setup() {
  console.log('동시 주문 부하 테스트 준비 중');
  
  // 테스트 사용자 생성
  for (const user of users) {
    const signupPayload = JSON.stringify({
      username: user.username,
      email: `${user.username}@example.com`,
      password: user.password
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
      },
    };

    const signupRes = http.post(`${BASE_URL}:8001/signup`, signupPayload, params);
    if (signupRes.status === 201 || signupRes.status === 400) {
      // 400은 이미 가입된 사용자일 수 있음
      console.log(`사용자 생성/확인 완료: ${user.username}`);
    }
  }
  
  console.log('동시 주문 부하 테스트 준비 완료');
  return users;
}

// 가상 사용자(VU) 스크립트 - 각 VU는 이 함수를 실행
export default function(usersData) {
  // 랜덤 사용자 선택
  const userIndex = Math.floor(Math.random() * users.length);
  const user = users[userIndex];
  
  // 토큰이 없으면 로그인
  if (!token && !login(user)) {
    console.log(`${user.username} 로그인 실패, 요청 건너뜁니다`);
    sleep(1);
    return;
  }
  
  // 같은 메뉴(ID=1)에 대한 주문 생성
  const orderPayload = JSON.stringify({
    items: [
      { menu_id: 1, quantity: 1 }  // 모든 사용자가 같은 메뉴 아이템을 주문
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

  // 주문 요청 전송
  const orderRes = http.post(`${BASE_URL}:8003/orders`, orderPayload, params);
  
  // 응답 검증
  check(orderRes, {
    'order created successfully': (r) => r.status === 201,
  });

  // 주문 실패 로깅
  if (orderRes.status !== 201) {
    console.log(`주문 생성 실패: ${orderRes.status}, ${orderRes.body}`);
    failedOrders.add(1);
  } else {
    const orderData = JSON.parse(orderRes.body);
    console.log(`주문 생성 성공: ${orderData.id}, 상태: ${orderData.status}`);
    successfulOrders.add(1);
  }

  // 요청 간 짧은 지연
  sleep(0.5);
}

// 테스트 종료 후 실행
export function teardown() {
  console.log('동시 주문 부하 테스트 완료');
} 