FROM node:18-alpine
RUN apk add --no-cache git
WORKDIR /app
COPY ./package.json ./package.json
COPY ./package-lock.json ./package-lock.json
RUN npm install
COPY . .
EXPOSE 8545
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0"]