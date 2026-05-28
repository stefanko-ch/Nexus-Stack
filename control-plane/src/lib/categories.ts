export const CATEGORIES: Record<string, { name: string; description: string }> = {
  'core': { name: 'Core Infrastructure', description: 'Essential services that keep your Nexus Stack running. These cannot be disabled.' },
  'databases': { name: 'Databases', description: 'Relational and analytical database engines for storing and querying structured data.' },
  'storage': { name: 'Object Storage', description: 'S3-compatible object storage systems for data lakes, backups, and file management.' },
  'db-management': { name: 'Database Management', description: 'Web-based tools for administering, browsing, and managing your databases and object storage.' },
  'orchestration': { name: 'Data Orchestration', description: 'Platforms for building, scheduling, and monitoring data pipelines and ETL/ELT workflows.' },
  'streaming': { name: 'Stream Processing', description: 'Engines and frameworks for real-time data processing, CDC, and streaming pipelines.' },
  'messaging': { name: 'Message Brokers', description: 'Event streaming platforms and management UIs for Kafka/Redpanda message brokers.' },
  'analytics': { name: 'Analytics & BI', description: 'Business intelligence, metadata management, and distributed query engines.' },
  'data-quality': { name: 'Data Quality', description: 'Tools for testing, validating, and monitoring the quality of your data.' },
  'ai-ml': { name: 'AI & Machine Learning', description: 'LLM inference, AI workflow builders, and machine learning platforms.' },
  'dev-tools': { name: 'Development Tools', description: 'IDEs, notebooks, API testing platforms, and developer utilities.' },
  'ci-cd': { name: 'CI/CD & Automation', description: 'Continuous integration, deployment pipelines, and workflow automation tools.' },
  'low-code': { name: 'Low-Code Platforms', description: 'Build internal tools, CRUD apps, and spreadsheet interfaces without extensive coding.' },
  'observability': { name: 'Observability', description: 'Monitoring agents, log pipelines, and uptime tracking for your infrastructure.' },
  'knowledge': { name: 'Knowledge & Docs', description: 'Wiki platforms and knowledge bases.' },
  'project-management': { name: 'Project Management', description: 'Kanban boards, issue trackers, and project-planning tools for organizing work.' },
  'visual-tools': { name: 'Visual Tools', description: 'Diagramming, whiteboard, and visual collaboration tools.' },
  'server-access': { name: 'Server Access', description: 'Tools for accessing your server via browser-based terminals and Git proxies.' },
};

export const CATEGORY_ORDER = [
  'core', 'databases', 'storage', 'db-management', 'orchestration', 'streaming',
  'messaging', 'analytics', 'data-quality', 'ai-ml', 'dev-tools',
  'ci-cd', 'low-code', 'observability', 'knowledge', 'project-management',
  'visual-tools', 'server-access',
];
