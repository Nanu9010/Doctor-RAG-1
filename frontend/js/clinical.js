// Navigation logic
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        
        const targetId = item.getAttribute('data-target');
        document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
        document.getElementById(targetId).classList.remove('hidden');
    });
});

// Set query from suggestion chips
function setQuery(text) {
    document.getElementById('clinicalQuery').value = text;
    document.getElementById('clinicalQuery').focus();
}

// Simulated API call for querying
async function submitQuery() {
    const query = document.getElementById('clinicalQuery').value.trim();
    if (!query) return;

    document.getElementById('answerCard').classList.add('hidden');
    document.getElementById('loadingState').classList.remove('hidden');
    document.getElementById('askBtn').disabled = true;

    try {
        // Here you would implement your actual Fetch API call to the backend
        /*
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, doc_id: document.getElementById('docSelect').value })
        });
        const data = await response.json();
        */
        
        // Simulating processing delay
        await new Promise(r => setTimeout(r, 1200)); 

        document.getElementById('loadingState').classList.add('hidden');
        document.getElementById('answerCard').classList.remove('hidden');
        
        // Mock response data mapping
        document.getElementById('answerText').innerHTML = `
            Based on the clinical guidelines, <strong>${query}</strong> is typically managed with appropriate pharmacological interventions.
            The primary indicated treatment involves continuous monitoring and adherence to prescribed ACE inhibitors and beta-blockers.
        `;
        
        // Mock confidence calculation
        const badge = document.getElementById('confidenceBadge');
        badge.className = 'confidence-badge high'; // Reset
        badge.textContent = 'High Confidence';
        
        document.getElementById('sourceList').innerHTML = `
            <div class="source-item">Page 4: "Standard pharmacological intervention includes ACE inhibitors..."</div>
        `;
    } catch (e) {
        console.error("Query failed", e);
        alert("An error occurred while fetching the response.");
    } finally {
        document.getElementById('askBtn').disabled = false;
    }
}

function queryDoc(docId) {
    document.querySelector('[data-target="view-ask"]').click();
    document.getElementById('docSelect').value = docId;
}

function uploadDocument() {
    // In reality this would open a file input dialog and handle multipart form data fetch
    alert("Upload dialog opened. Document processing notification will follow upon completion.");
}
