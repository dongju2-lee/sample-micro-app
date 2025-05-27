FROM node:18-alpine

WORKDIR /app

# package.json과 package-lock.json을 복사
COPY package*.json ./

# 종속성 설치
RUN npm install --production

# 소스 코드 복사
COPY . .

# 포트 노출
EXPOSE 3000

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# 애플리케이션 시작
CMD ["npm", "start"] 