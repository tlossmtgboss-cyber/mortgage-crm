import express from 'express';
import { PrismaClient } from '@prisma/client';
import { v4 as uuidv4 } from 'uuid';

const app = express();
const prisma = new PrismaClient();
const PORT = 3000;

app.use(express.json());

// ✅ Root route for browser testing
app.get('/', (req, res) => {
  res.send('Welcome to the CRM backend!');
});

// ✅ POST /leads route
app.post('/leads', async (req, res) => {
  try {
    const {
      first_name,
      last_name,
      email,
      phone,
      source,
      score,
      assigned_to,
      status,
    } = req.body;

    const newLead = await prisma.leads.create({
      data: {
        id: uuidv4(),
        first_name,
        last_name,
        email,
        phone,
        source,
        score: score ? Number(score) : null,
        assigned_to,
        status,
        created_at: new Date(),
      },
    });

    res.status(201).json(newLead);
  } catch (error) {
    console.error('Error creating lead:', error);
    res.status(500).json({ error: 'Failed to create lead' });
  }
});

// ✅ Start the server
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});