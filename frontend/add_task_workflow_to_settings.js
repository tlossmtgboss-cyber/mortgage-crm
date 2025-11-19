const fs = require('fs');
const path = require('path');

const settingsPath = path.join(__dirname, 'src/pages/Settings.js');
let content = fs.readFileSync(settingsPath, 'utf8');

// 1. Add import at the top
const importLine = "import TaskWorkflowManager from '../components/TaskWorkflowManager';";
const importLocation = content.indexOf("import './Settings.css';");
if (importLocation !== -1 && !content.includes(importLine)) {
  content = content.replace(
    "import './Settings.css';",
    importLine + "\nimport './Settings.css';"
  );
  console.log('✓ Added import statement');
}

// 2. Add sidebar button after experiments button
const sidebarButton = `
          <button
            className={\`sidebar-btn \${activeSection === 'task-workflow' ? 'active' : ''}\`}
            onClick={() => setActiveSection('task-workflow')}
          >
            <span className="icon">📋</span>
            <span>Task & Workflow Management</span>
          </button>
`;

const experimentsButton = content.indexOf(`className={\`sidebar-btn \${activeSection === 'experiments' ? 'active' : ''}\`}`);
if (experimentsButton !== -1) {
  // Find the closing </button> for experiments
  const experimentsEnd = content.indexOf('</button>', experimentsButton);
  const insertPoint = content.indexOf('\n', experimentsEnd) + 1;

  if (!content.includes('task-workflow')) {
    content = content.slice(0, insertPoint) + sidebarButton + content.slice(insertPoint);
    console.log('✓ Added sidebar button');
  }
}

// 3. Add section rendering after experiments section
const sectionRender = `
          {activeSection === 'task-workflow' && (
            <TaskWorkflowManager />
          )}
`;

const experimentsSection = content.indexOf("{activeSection === 'experiments' && (");
if (experimentsSection !== -1) {
  // Find the closing )}
  let braceCount = 0;
  let pos = experimentsSection;
  let foundStart = false;

  while (pos < content.length) {
    if (content[pos] === '{') {
      braceCount++;
      foundStart = true;
    }
    if (content[pos] === '}') {
      braceCount--;
      if (foundStart && braceCount === 0) {
        // Find the closing parenthesis and newline
        const closingParen = content.indexOf(')', pos);
        const insertPoint = content.indexOf('\n', closingParen) + 1;

        if (!content.includes('task-workflow')) {
          content = content.slice(0, insertPoint) + sectionRender + content.slice(insertPoint);
          console.log('✓ Added section rendering');
        }
        break;
      }
    }
    pos++;
  }
}

// Write the modified content
fs.writeFileSync(settingsPath, content);
console.log('\n✅ Settings.js updated successfully!');
console.log('Task & Workflow Management section has been added to the Settings page.');
