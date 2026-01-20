// Popup script - handles user interactions
const CRM_API_URL = 'https://api.perenniaai.com/api/v1/migrations';

// Source URLs
const SOURCE_URLS = {
  fannie_mae: 'https://my.mortgageguidelines.com/fannie-mae-updates/',
  freddie_mac: 'https://my.mortgageguidelines.com/freddie-mac-updates/',
  fha: 'https://my.mortgageguidelines.com/fha-updates/',
  va: 'https://my.mortgageguidelines.com/va-updates/',
  usda: 'https://my.mortgageguidelines.com/usda-updates/'
};

// Check current page on load
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const currentUrl = tabs[0].url;
  const pageStatus = document.getElementById('pageStatus');

  if (currentUrl.includes('my.mortgageguidelines.com')) {
    // Detect which source page
    let sourcePage = 'Unknown';
    for (const [source, url] of Object.entries(SOURCE_URLS)) {
      if (currentUrl.includes(source.replace('_', '-'))) {
        sourcePage = source.replace('_', ' ').toUpperCase();
        break;
      }
    }
    pageStatus.innerHTML = `✅ On Mortgage Guidelines<br><strong>${sourcePage}</strong>`;
  } else {
    pageStatus.innerHTML = '⚠️ Not on mortgageguidelines.com<br>Please navigate to the site first.';
    document.getElementById('scrapeBtn').disabled = true;
  }
});

// Scrape current page
document.getElementById('scrapeBtn').addEventListener('click', async () => {
  const btn = document.getElementById('scrapeBtn');
  const statusDiv = document.getElementById('status');

  btn.disabled = true;
  btn.textContent = '⏳ Extracting...';
  statusDiv.innerHTML = '<div class="status info">Scraping current page...</div>';

  try {
    // Get current tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Execute content script to extract data
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractGuidelinesFromPage
    });

    const guidelines = results[0].result;

    if (guidelines && guidelines.length > 0) {
      // Send to CRM
      await sendToCRM(guidelines);

      statusDiv.innerHTML = `<div class="status success">✅ Successfully extracted ${guidelines.length} updates!</div>`;
      displayResults(guidelines);
    } else {
      statusDiv.innerHTML = '<div class="status error">❌ No updates found on this page</div>';
    }
  } catch (error) {
    console.error('Scrape error:', error);
    statusDiv.innerHTML = `<div class="status error">❌ Error: ${error.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 Extract & Sync to CRM';
  }
});

// Scrape all sources
document.getElementById('scrapeAllBtn').addEventListener('click', async () => {
  const btn = document.getElementById('scrapeAllBtn');
  const statusDiv = document.getElementById('status');
  const progressDiv = document.getElementById('progress');
  const progressBar = document.getElementById('progressBar');

  btn.disabled = true;
  btn.textContent = '⏳ Scraping All...';
  progressDiv.style.display = 'block';

  const allGuidelines = [];
  const sourceCount = {};
  const sources = Object.entries(SOURCE_URLS);

  for (let i = 0; i < sources.length; i++) {
    const [sourceName, sourceUrl] = sources[i];

    statusDiv.innerHTML = `<div class="status info">Scraping ${sourceName.replace('_', ' ').toUpperCase()}...</div>`;
    progressBar.style.width = `${((i + 1) / sources.length) * 100}%`;

    try {
      // Create new tab
      const tab = await chrome.tabs.create({ url: sourceUrl, active: false });

      // Wait for page to load
      await new Promise(resolve => {
        chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
          if (tabId === tab.id && info.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve();
          }
        });
      });

      // Wait a bit for dynamic content
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Extract data
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractGuidelinesFromPage
      });

      const guidelines = results[0].result || [];
      allGuidelines.push(...guidelines);
      sourceCount[sourceName] = guidelines.length;

      // Close tab
      await chrome.tabs.remove(tab.id);

    } catch (error) {
      console.error(`Error scraping ${sourceName}:`, error);
      sourceCount[sourceName] = 0;
    }
  }

  // Send all to CRM
  if (allGuidelines.length > 0) {
    await sendToCRM(allGuidelines);
    statusDiv.innerHTML = `<div class="status success">✅ Scraped ${allGuidelines.length} total updates from all sources!</div>`;
    displayResults(allGuidelines, sourceCount);
  } else {
    statusDiv.innerHTML = '<div class="status error">❌ No updates found across all sources</div>';
  }

  progressDiv.style.display = 'none';
  btn.disabled = false;
  btn.textContent = '📚 Scrape All Sources';
});

// Function to extract guidelines from page (runs in page context)
function extractGuidelinesFromPage() {
  const guidelines = [];
  const currentUrl = window.location.href;

  // Detect source from URL
  let source = 'unknown';
  if (currentUrl.includes('fannie-mae')) source = 'fannie_mae';
  else if (currentUrl.includes('freddie-mac')) source = 'freddie_mac';
  else if (currentUrl.includes('fha')) source = 'fha';
  else if (currentUrl.includes('va-updates')) source = 'va';
  else if (currentUrl.includes('usda')) source = 'usda';

  // Find all update entries
  const articles = document.querySelectorAll('article, .post, .entry, .update-item');

  articles.forEach((article, index) => {
    try {
      // Extract title
      const titleElem = article.querySelector('h1, h2, h3, h4, .entry-title, .post-title');
      const title = titleElem ? titleElem.textContent.trim() : '';

      if (!title || title.length < 5) return;

      // Extract URL
      const linkElem = article.querySelector('a[href]');
      const url = linkElem ? linkElem.href : currentUrl;

      // Extract date
      const dateElem = article.querySelector('time, .date, .published, .entry-date');
      let dateStr = '';
      if (dateElem) {
        dateStr = dateElem.getAttribute('datetime') || dateElem.textContent.trim();
      }

      // Extract description
      const descElem = article.querySelector('p, .excerpt, .summary, .description');
      const description = descElem ? descElem.textContent.trim().substring(0, 500) : title;

      // Extract section code
      const codeMatch = title.match(/(SEL|ML|CIRC|BULL|RD)[\s-]?\d{4}[-]?\d{1,2}/i);
      const sectionCode = codeMatch ? codeMatch[0] : null;

      guidelines.push({
        source,
        title,
        section_code: sectionCode,
        description,
        url,
        date_str: dateStr,
        scraped_from_browser: true
      });
    } catch (error) {
      console.error('Error extracting guideline:', error);
    }
  });

  // Limit to top 5 per page
  return guidelines.slice(0, 5);
}

// Send guidelines to CRM
async function sendToCRM(guidelines) {
  try {
    const response = await fetch(`${CRM_API_URL}/import-browser-guidelines`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ guidelines })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const result = await response.json();
    console.log('CRM sync result:', result);
    return result;
  } catch (error) {
    console.error('Failed to send to CRM:', error);
    throw error;
  }
}

// Display extraction results
function displayResults(guidelines, sourceCount = null) {
  const resultsDiv = document.getElementById('results');
  const sourceResultsDiv = document.getElementById('sourceResults');
  const totalCountDiv = document.getElementById('totalCount');

  resultsDiv.style.display = 'block';
  totalCountDiv.textContent = guidelines.length;

  if (sourceCount) {
    let html = '';
    for (const [source, count] of Object.entries(sourceCount)) {
      html += `
        <div class="source-status">
          <span>${source.replace('_', ' ').toUpperCase()}</span>
          <span class="source-count">${count}</span>
        </div>
      `;
    }
    sourceResultsDiv.innerHTML = html;
  } else {
    // Group by source
    const grouped = {};
    guidelines.forEach(g => {
      grouped[g.source] = (grouped[g.source] || 0) + 1;
    });

    let html = '';
    for (const [source, count] of Object.entries(grouped)) {
      html += `
        <div class="source-status">
          <span>${source.replace('_', ' ').toUpperCase()}</span>
          <span class="source-count">${count}</span>
        </div>
      `;
    }
    sourceResultsDiv.innerHTML = html;
  }
}
