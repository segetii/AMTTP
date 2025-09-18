.PHONY: start stop deploy-contracts compile test

start:
    docker-compose up -d
    @echo 'Services started: Hardhat(8545), Helia(8080), MongoDB(27017), MinIO(9001), Vault(8200)'

stop:
    docker-compose down
    @echo 'Services stopped'

deploy-contracts:
    npx hardhat run scripts/deploy.js --network hardhat
    npx hardhat run scripts/deploy.js --network sepolia

compile:
    npx hardhat compile

test:
    npx hardhat test
