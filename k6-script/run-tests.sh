#!/bin/bash

# k6 테스트 실행 스크립트
# 도커를 통해 k6를 실행하기 위한 쉘 스크립트입니다.

echo "===== k6 로드 테스트 실행 스크립트 ====="
echo "이 스크립트는 도커를 통해 k6를 실행합니다."
echo "-------------------------------------"

# 현재 디렉토리
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 모든 테스트를 실행할지, 특정 테스트만 실행할지 결정
run_all=false
test_file=""

# 인자가 없으면 사용법 표시
if [ $# -eq 0 ]; then
  echo "사용법: $0 [all|파일명.js]"
  echo "  all: 모든 테스트 스크립트를 차례로 실행"
  echo "  파일명.js: 특정 테스트 스크립트만 실행"
  echo "예: $0 all"
  echo "예: $0 01-chaos-engineering-test.js"
  exit 1
fi

# 인자 처리
if [ "$1" = "all" ]; then
  run_all=true
else
  test_file="$1"
  # 파일 존재 확인
  if [ ! -f "$SCRIPT_DIR/$test_file" ]; then
    echo "오류: $test_file 파일을 찾을 수 없습니다."
    exit 1
  fi
fi

# 도커 설치 확인
if ! command -v docker &> /dev/null; then
  echo "오류: 도커가 설치되어 있지 않습니다. 도커를 설치한 후 다시 시도하세요."
  exit 1
fi

# k6 이미지 확인 및 다운로드
echo "k6 도커 이미지 확인 중..."
if ! docker image inspect grafana/k6 &> /dev/null; then
  echo "k6 도커 이미지를 다운로드합니다..."
  docker pull grafana/k6
fi

# 테스트 실행 함수
run_test() {
  local test_script=$1
  echo ""
  echo "===== 테스트 실행: $test_script ====="
  echo "테스트를 중단하려면 Ctrl+C를 누르세요."
  
  docker run --rm \
    --network=host \
    -v "$SCRIPT_DIR:/scripts" \
    grafana/k6 run "/scripts/$test_script" \
    --summary-export="/scripts/results-${test_script%.js}.json"
    
  local exit_code=$?
  if [ $exit_code -ne 0 ]; then
    echo "테스트 실행 중 오류가 발생했습니다. 종료 코드: $exit_code"
  else
    echo "테스트 완료: $test_script"
    echo "결과가 results-${test_script%.js}.json 파일로 저장되었습니다."
  fi
  
  return $exit_code
}

# 테스트 스크립트 목록
test_scripts=(
  "01-chaos-engineering-test.js"
  "02-concurrent-orders-test.js"
  "03-cancel-reorder-test.js"
  "04-caching-effect-test.js"
  "05-microservice-communication-test.js"
)

# 모든 테스트 실행 또는 특정 테스트 실행
if [ "$run_all" = true ]; then
  echo "모든 테스트를 차례로 실행합니다..."
  
  for script in "${test_scripts[@]}"; do
    # 파일 존재 확인
    if [ -f "$SCRIPT_DIR/$script" ]; then
      run_test "$script"
      echo ""
      echo "5초 후 다음 테스트를 실행합니다..."
      sleep 5
    else
      echo "경고: $script 파일이 존재하지 않아 건너뜁니다."
    fi
  done
  
  echo ""
  echo "===== 모든 테스트 실행 완료 ====="
else
  # 특정 테스트만 실행
  run_test "$test_file"
fi

echo ""
echo "테스트 실행이 완료되었습니다."
echo "결과 파일은 $SCRIPT_DIR 디렉토리에 저장되었습니다." 