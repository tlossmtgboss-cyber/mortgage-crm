import { PrismaClient } from '@prisma/client';
import { v4 as uuidv4 } from 'uuid';

const prisma = new PrismaClient();

async function main() {
  const newLead = await prisma.leads.create({
    data: {
      id: uuidv4(),
      first_name: 'Jane',
      last_name: 'Doe',
      email: 'jane.doe@example.com',
      phone: '555-1234',
      source: 'Website',
      score: 85,
      assigned_to: null,
      status: 'New',
      created_at: new Date(),
    },
  });

  console.log('New lead created:', newLead);
}

main()
  .catch((e) => console.error(e))
  .finally(async () => {
    await prisma.$disconnect();
  });