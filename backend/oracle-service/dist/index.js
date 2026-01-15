import express from "express";
import cors from "cors";
import mongoose from "mongoose";
import { kycRouter } from "./routes/kyc.js";
import { riskRouter } from "./routes/risk.js";
import { txRouter } from "./routes/tx.js";
const app = express();
app.use(cors());
app.use(express.json());
// Basic health endpoint for container health checks
app.get('/health', (_req, res) => {
    res.status(200).json({ status: 'ok' });
});
app.use("/kyc", kycRouter);
app.use("/risk", riskRouter);
app.use("/tx", txRouter);
async function start() {
    await mongoose.connect(process.env.MONGO_URI);
    const port = process.env.PORT || 3000;
    app.listen(port, () => console.log(`oracle-service listening on ${port}`));
}
// Only start the server if this file is executed directly
if (process.env.NODE_ENV !== 'test') {
    start();
}
export { app };
