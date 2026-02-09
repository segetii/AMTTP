@echo off
cd /d c:\amttp
echo Running ZkNAF Verifier Tests...
call npx hardhat test test/ZkNAFVerifierRouter.test.mjs
echo.
echo Done.
pause
