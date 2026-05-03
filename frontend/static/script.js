document.getElementById('runBtn').addEventListener('click', async () => {
    const taskInput = document.getElementById('taskInput');
    const task = taskInput.value.trim();
    if (!task) return;

    const runBtn = document.getElementById('runBtn');
    const statusArea = document.getElementById('statusArea');
    const resultsArea = document.getElementById('resultsArea');
    const statusText = document.getElementById('statusText');

    runBtn.disabled = true;
    statusArea.style.display = 'block';
    resultsArea.style.display = 'none';

    try {
        const response = await fetch('/run_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task })
        });

        const { task_id } = await response.json();
        pollStatus(task_id);
    } catch (err) {
        alert('Error starting task: ' + err.message);
        runBtn.disabled = false;
    }
});

async function pollStatus(taskId) {
    const statusText = document.getElementById('statusText');
    const runBtn = document.getElementById('runBtn');

    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/task_status/${taskId}`);
            const data = await response.json();

            statusText.innerText = data.status.charAt(0).toUpperCase() + data.status.slice(1) + '...';

            if (data.status === 'completed') {
                clearInterval(interval);
                displayResults(data.results);
                runBtn.disabled = false;
            } else if (data.status.includes('error')) {
                clearInterval(interval);
                alert('Task failed: ' + data.error);
                runBtn.disabled = false;
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 2000);
}

function displayResults(results) {
    const resultsArea = document.getElementById('resultsArea');
    const baseTokensEl = document.getElementById('baseTokens');
    const optTokensEl = document.getElementById('optTokens');
    const reductionLabel = document.getElementById('reductionLabel');
    const comparisonBody = document.getElementById('comparisonBody');
    const outcomeText = document.getElementById('outcomeText');
    const reportArea = document.getElementById('reportArea');

    resultsArea.style.display = 'block';
    comparisonBody.innerHTML = '';

    let baseTotal = 0;
    let optTotal = 0;
    let optLarge = 0;
    let optSmall = 0;

    results.forEach(res => {
        const row = document.createElement('tr');
        if (res.error) {
            row.innerHTML = `<td colspan="5" style="color: #ef4444">Error in ${res.mode}: ${res.error}</td>`;
        } else {
            const large = res.metrics.large.total;
            const small = res.metrics.small.total;
            const total = large + small;

            if (res.mode === 'Baseline') {
                baseTotal = total;
            } else {
                optTotal = total;
                optLarge = large;
                optSmall = small;
            }

            row.innerHTML = `
                <td>${res.mode}</td>
                <td>${large.toLocaleString()}</td>
                <td>${small.toLocaleString()}</td>
                <td>${res.success ? '100%' : '0%'}</td>
                <td style="color: ${res.success ? '#4ade80' : '#ef4444'}">${res.success ? 'Success' : 'Fail'}</td>
            `;
            
            if (res.mode === 'Optimised') {
                outcomeText.innerText = res.output;
                reportArea.style.display = 'block';
            }
        }
        comparisonBody.appendChild(row);
    });

    baseTokensEl.innerText = baseTotal.toLocaleString();
    optTokensEl.innerText = optTotal.toLocaleString();

    if (baseTotal > 0) {
        const reduction = ((baseTotal - optLarge) / baseTotal * 100).toFixed(1);
        reductionLabel.innerText = `${reduction}% Reduction (Large Model)`;
    }
}
