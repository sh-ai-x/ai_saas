import { catalogSchema } from './contracts';
export const seedFaqs = catalogSchema.parse([
  { id: 'guides', category: 'guides', question: 'Where are the setup guides?', aliases: ['setup guides', 'documentation'], answer: 'Open Guides from the main navigation to find setup instructions and troubleshooting information.' },
  { id: 'workspace', category: 'product', question: 'Where is the workspace?', aliases: ['open workspace', 'workspace'], answer: 'Open Workspace from the main navigation to access the application console.' },
  { id: 'support', category: 'support', question: 'How can I get more help?', aliases: ['support', 'help'], answer: 'Use the Support guide link below for setup and troubleshooting help. This FAQ cannot access or change your account.' },
]);
