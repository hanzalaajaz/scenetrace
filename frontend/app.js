const main = document.querySelector('#main');
const dialog = document.querySelector('#modal');
const state = {locations: [], recordings: [], people: [], reviews: [], overview: {}};
let poll = null;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const badge = value => `<span class="badge ${esc(value)}">${esc(value || 'unknown')}</span>`;
const offset = value => `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toFixed(1).padStart(4, '0')}`;
const locationName = id => state.locations.find(item => item.id === id)?.label || 'Saved view';
const pageName = {overview:'Analyze video',locations:'Train locations',recordings:'Recordings',people:'People',search:'Search person',reviews:'Review matches',agents:'Agent center'};

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try { const result = await response.json(); detail = typeof result.detail === 'string' ? result.detail : 'Please check the form fields.'; } catch {}
    throw new Error(detail);
  }
  return response.json();
}
const jsonOptions = (method, data) => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
function toast(message, error = false) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.className = `visible${error ? ' error' : ''}`;
  setTimeout(() => element.className = '', error ? 8000 : 4500);
}
function heading(title, subtitle, action = '') {
  return `<div class="page-heading"><div><div class="eyebrow">SCENETRACE / LOCAL WORKSPACE</div><h1>${title}</h1><p class="subtext">${subtitle}</p></div>${action}</div>`;
}
function empty(title, description, symbol = '◈') {
  return `<div class="empty"><div class="empty-symbol">${symbol}</div><h3>${title}</h3><p>${description}</p></div>`;
}
function metrics() {
  return `<div class="metrics">${[['Saved locations',state.overview.locations,'Ready for recognition','⌖'],['Recordings',state.overview.recordings,'Your video library','▻'],['Person groups',state.overview.people,'Provisional & reviewed','♙'],['Tracks to review',state.overview.reviews,'Keep the connections accurate','⇄']].map(([title,value,foot,icon]) => `<div class="metric"><span class="metric-label">${title}</span><span class="metric-icon">${icon}</span><div class="metric-value">${value ?? 0}</div><span class="metric-foot">${foot}</span></div>`).join('')}</div>`;
}
function uploadForm() {
  return `<form id="upload-form"><div class="section-label"><div><h2>Upload a video to analyze</h2><p class="subtext">Find its saved location and detect the people in this recording.</p></div><span class="tag">STEP 2 · ANALYZE</span></div>
  <label class="dropzone" for="recording-file"><span class="drop-icon">↥</span><strong id="upload-name">Choose the video you want to analyze</strong><p>Drop it here or <span class="browse">browse files</span> on your computer</p><p>MP4, MOV, AVI, MKV, WEBM · Up to 250 MB</p><input type="file" id="recording-file" name="file" accept="video/*,.mkv,.avi" required></label>
  <details><summary>Recording start time · optional</summary><div class="form-grid"><label class="field">Start date and time<input type="datetime-local" name="start_time" step="1"></label><label class="field">UTC offset<select name="utc_offset"><option>+05:00</option><option>+00:00</option><option>+05:30</option><option>+04:00</option><option>-04:00</option><option>-05:00</option></select></label></div><p class="subtext">Leave blank if unknown. Observation times will use playback offsets.</p></details>
  <div class="upload-actions"><p class="upload-note">Single-view clips only. Your footage stays on this computer.</p><button class="btn primary" type="submit">Analyze recording <span>↗</span></button></div><p class="form-status" aria-live="polite"></p></form>`;
}
function recordingTable(rows) {
  if (!rows.length) return empty('Your first recording belongs here', 'Upload footage to start building a source-linked observation history.', '▤');
  return `<div class="table-wrap"><table><thead><tr><th>Recording</th><th>Location</th><th>Status</th><th>Length</th><th></th></tr></thead><tbody>${rows.map(row => `<tr><td class="file-cell">▻ &nbsp; ${esc(row.filename)}</td><td>${esc(row.location_label || 'Not assigned')}</td><td>${badge(row.status)}</td><td>${offset(row.duration)}</td><td><a class="btn small" href="#recordings/${esc(row.id)}">Open ↗</a> <button type="button" class="btn small danger" data-action="delete-recording" data-id="${row.id}" ${["queued","processing"].includes(row.status)?"disabled":""}>Delete</button></td></tr>`).join('')}</tbody></table></div>`;
}
function workflowGuide() {
  return `<div class="workflow-guide"><a href="#locations"><span class="step-no">1</span><div><strong>Train locations</strong><p>Upload a reference video, name its location, and save it once.</p></div><span>→</span></a><a href="#overview"><span class="step-no">2</span><div><strong>Analyze video</strong><p>Upload a later recording. Its saved location is recognized automatically when the view matches.</p></div><span>→</span></a></div>`;
}
function overview() {
  main.innerHTML = heading('Analyze your video.', 'Upload a recording to find its location and the people observed in it.') + workflowGuide() + metrics() +
  (!state.locations.length ? '<div class="notice warning"><strong>First time here?</strong> Save a labeled reference video before analyzing later recordings. <a class="btn small" href="#locations">1. Train your first location →</a></div>' : '') +
  `<div class="dashboard-grid"><section class="panel panel-pad">${uploadForm()}<div class="auto-note">✧ <span>Saved views are recognized automatically. Uncertain matches stay open for review.</span></div></section><section class="panel steps"><h2>A little setup. A lot more context.</h2>${[
    ['01','Teach it your places','Label a reference video once. SceneTrace remembers that view for later recordings.'],
    ['02','Let the footage connect','Upload a recording. Find the saved location and detect people within the frame.'],
    ['03','Review the bigger picture','Check possible returning people and follow their observations across locations.']
  ].map(([num,title,body]) => `<div class="step"><span class="step-no">${num}</span><div><h3>${title}</h3><p>${body}</p></div></div>`).join('')}</section></div>
  <section class="section"><div class="section-label"><div><h2>Recent recordings</h2><p class="subtext">Your latest footage and its analysis status.</p></div><a href="#recordings" class="btn small">View library →</a></div><div class="panel">${recordingTable(state.recordings.slice(0, 4))}</div></section>`;
  bindUpload();
}
function locationsPage() {
  main.innerHTML = heading('Train your locations.', 'This is where you upload reference videos and save their location labels once.', '<button class="btn primary" data-action="add-location">+ Upload training video</button>') + workflowGuide() +
  (!state.locations.length ? `<section class="panel panel-pad">${empty('Upload your first location reference', 'Choose a video of one place, enter its location name and camera label, then save. Later recordings can reuse that label automatically.', '⌖')}<button class="btn primary" data-action="add-location">Upload training video + label location →</button></section>` :
  `<div class="cards">${state.locations.map(row => `<article class="panel"><img class="location-img" src="${esc(row.preview_url)}" alt="Reference view for ${esc(row.label)}"><div class="card-body"><div class="section-label"><h2>${esc(row.label)}</h2>${badge('saved')}</div><p class="subtext">${esc(row.camera_label)} · ${row.reference_count} reference set${row.reference_count === 1 ? '' : 's'}</p><div class="spacer"></div><div class="actions"><button class="btn small" data-action="add-reference" data-id="${row.id}">+ Reference</button><button class="btn small" data-action="rename-location" data-id="${row.id}">Rename</button></div></div></article>`).join('')}</div>`) +
  `<div class="notice">Different lighting? Add another reference to the same saved view. A moved camera needs a separate view. The system recognizes the background and viewpoint, rather than the physical camera device.</div><a class="btn primary" href="#overview">Next: upload a video to analyze →</a>`;
}
function recordingsPage() {
  main.innerHTML = heading('Your recording library.', 'Find the source behind every appearance and location observation.', '<button class="btn primary" data-action="upload">+ Add recording</button>') +
  `<div class="filter-bar"><input class="search" id="recording-search" placeholder="Search recordings or locations…" aria-label="Search recordings"><button class="btn small" data-action="refresh">↻ Refresh</button></div><div class="panel" id="recording-table">${recordingTable(state.recordings)}</div>`;
  document.querySelector('#recording-search').addEventListener('input', event => {
    const term = event.target.value.toLowerCase();
    document.querySelector('#recording-table').innerHTML = recordingTable(state.recordings.filter(row => `${row.filename} ${row.location_label || ''}`.toLowerCase().includes(term)));
  });
}
async function recordingDetail(id) {
  const row = await api(`/api/recordings/${id}`);
  if (location.hash !== `#recordings/${id}`) return;
  const active = ['queued','processing'].includes(row.status);
  const locationPanel = `<section class="panel panel-pad"><div class="eyebrow">VIEW RECOGNITION</div><h2>${esc(row.location_label || 'Location not assigned')}</h2><p class="subtext">${esc(row.camera_label || 'No confirmed camera')} &nbsp; ${badge(row.location_status)}</p><div class="spacer"></div><p class="subtext">${row.location_status === 'recognized' ? 'Automatically matched to a saved reference view.' : row.location_status === 'confirmed' ? 'This location was confirmed by a reviewer.' : 'Your saved labels are available, but this recording does not match their reference angles reliably. Teach this angle once using one of your saved locations.'}</p>${row.scene_scores.map(candidate => `<p class="subtext">${esc(locationName(candidate.location_id))} · score ${candidate.score.toFixed(2)} · support ${Math.round(candidate.support * 100)}%</p>`).join('')}<div class="spacer"></div><button class="btn small" data-action="correct-location" data-id="${id}" ${active ? 'disabled' : ''}>Review location</button> <button class="btn small" data-action="teach-view" data-id="${id}" ${active?"disabled":""}>Teach this angle</button><div class="notice">${row.recorded_at ? `Recording start: ${esc(row.recorded_at)}` : 'Recording date unknown. Observations use video playback offsets.'}</div></section>`;
  main.innerHTML = heading(esc(row.filename), `${offset(row.duration)} seconds of source footage`, `<div class="actions"><a href="#recordings" class="btn">Library</a><button type="button" class="btn danger" data-action="delete-recording" data-id="${id}" ${active?'disabled':''}>Delete recording</button></div>`) +
    (active ? `<div class="panel panel-pad"><h2>Analyzing your recording</h2><p class="subtext">${esc(row.message)}</p><div class="progress"><div style="width:${Math.round(row.progress * 100)}%"></div></div><span class="subtext">${Math.round(row.progress * 100)}% · Processing continues while you browse.</span></div>` :
    `<div class="recording-layout"><div><div class="video-shell"><div class="video-stage"><video id="source-video" controls preload="metadata" src="${row.media_url}">Your browser cannot play this video.</video><svg id="detection-overlay" aria-label="Detected person bounding boxes"></svg></div></div><div class="player-toolbar"><label><input type="checkbox" id="show-boxes" checked> Person boxes + IDs</label><span id="visible-count">Loading detections…</span></div><p id="player-status" class="video-caption">Person-only detections are shown at analyzed frames. Select View appearances for captured images and locations.</p></div>${locationPanel}</div>`) +
    (['failed','interrupted'].includes(row.status) ? `<div class="notice error">${esc(row.message)} <button class="btn small" data-action="retry" data-id="${id}">Retry analysis</button></div>` : '') +
    (!active ? `<section class="section"><div class="section-label"><h2>Detected person tracks <span class="tag">${row.tracks.length}</span></h2><div class="actions"><button class="btn small" data-action="reanalyze" data-id="${id}">Reanalyze with person detector</button><a href="#reviews" class="btn small">Review associations →</a></div></div><div class="panel">${row.tracks.length ? row.tracks.map(track => `<div class="track-row"><img class="person-crop" src="${track.thumbnail_url}" alt="Representative crop for track ${track.local_id}"><div class="track-info"><h3><a href="#people/${track.person_id}">${esc(track.label)}</a> · Track ${track.local_id}</h3><p>${offset(track.first_seen)} → ${offset(track.last_seen)} · ${track.sample_count} detection samples</p>${badge(track.match_status)}</div><button type="button" class="btn small" data-action="view-appearances" data-id="${track.person_id}">View appearances ▦</button></div>`).join('') : empty('No retained person tracks in this recording', 'Try reanalysis if these are results from the older detector. No detection does not prove absence.', '♙')}</div><p class="subtext">Detector: ${esc(row.detector_version || 'Legacy detector — reanalysis recommended')} · ${row.processed_frames || 0} frames analyzed</p></section>
    <details class="section"><summary>Recording management</summary><div class="notice">Deleting removes the source video, track observations, thumbnails, and dependent suggestions. Saved view references remain.</div><button class="btn danger" data-action="delete-recording" data-id="${id}">Delete this recording</button></details>` : '');
  if (active) poll = setTimeout(() => recordingDetail(id).catch(error => toast(error.message, true)), 1800);
  if (!active) await attachDetectionOverlay(id);
  if (!active && sessionStorage.getItem('seek-recording') === id) {
    const video = document.querySelector('#source-video');
    const target = Number(sessionStorage.getItem('seek-time') || 0);
    if(video){if(video.readyState>=1)video.currentTime=target;else video.addEventListener('loadedmetadata',()=>video.currentTime=target,{once:true});}
    sessionStorage.removeItem('seek-recording');
  }
}
async function attachDetectionOverlay(recordingId) {
  const video=document.querySelector('#source-video'), overlay=document.querySelector('#detection-overlay');
  if(!video || !overlay)return;
  const samples=await api(`/api/recordings/${recordingId}/detections`);
  if(!video.isConnected)return;
  function draw(){
    if(!video.isConnected || !video.videoWidth)return;
    overlay.setAttribute('viewBox',`0 0 ${video.videoWidth} ${video.videoHeight}`);
    let low=0,high=samples.length;
    while(low<high){const mid=(low+high)>>1;if(samples[mid].offset<video.currentTime)low=mid+1;else high=mid;}
    const near=[samples[low],samples[low-1]].filter(Boolean).sort((a,b)=>Math.abs(a.offset-video.currentTime)-Math.abs(b.offset-video.currentTime))[0];
    const visible=near && Math.abs(near.offset-video.currentTime)<=.12 ? samples.filter(row=>Math.abs(row.offset-near.offset)<.001) : [];
    document.querySelector('#visible-count').textContent=`${visible.length} person${visible.length===1?'':'s'} detected at this frame`;
    overlay.innerHTML=document.querySelector('#show-boxes').checked ? visible.map(row=>{
      const [x,y,w,h]=row.box, px=x*video.videoWidth,py=y*video.videoHeight,pw=w*video.videoWidth,ph=h*video.videoHeight;
      const font=Math.max(15,video.videoWidth*.024),textY=Math.max(font+5,py-8);
      const faceMarkup=row.face_box ? (()=>{const [fx,fy,fw,fh]=row.face_box;return `<rect x="${fx*video.videoWidth}" y="${fy*video.videoHeight}" width="${fw*video.videoWidth}" height="${fh*video.videoHeight}" fill="none" stroke="#ffdc75" stroke-width="2" stroke-dasharray="6 3"/>`;})() : '';
      return `${faceMarkup}<rect x="${px}" y="${py}" width="${pw}" height="${ph}" fill="none" stroke="#7cffb1" stroke-width="3"/><rect x="${px}" y="${textY-font-3}" width="${font*9}" height="${font+8}" fill="#143f2c"/><text x="${px+4}" y="${textY}" fill="white" font-size="${font}" font-family="sans-serif">${esc(row.label)} · ${Math.round(row.confidence*100)}%</text>`;
    }).join('') : '';
  }
  ['loadedmetadata','loadeddata','timeupdate','seeked','pause'].forEach(event=>video.addEventListener(event,draw));
  document.querySelector('#show-boxes').addEventListener('change',draw);
  video.addEventListener('error',()=>document.querySelector('#player-status').textContent='This browser cannot play this codec. View appearances still provides captured person images and locations.');
  video.addEventListener('play',()=>{
    const update=()=>{if(!video.isConnected || video.paused || video.ended)return;draw();if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(update);else requestAnimationFrame(update);};update();
  });
  if(!samples.length)document.querySelector('#visible-count').textContent='No box data · reanalyze older recordings';
  draw();
}
function peoplePage() {
  main.innerHTML = heading('Appearances, connected.', 'Anonymous person groups with source footage, locations, and observations.') +
  (!state.people.length ? `<div class="panel panel-pad">${empty('The timeline starts with a person', 'Analyze a video with visible people, then review appearances to connect the observations.', '♙')}</div>` :
  `<div class="cards">${state.people.map(person => `<a class="panel person-card" href="#people/${person.id}"><img src="${person.thumbnail_url}" alt="Representative person crop"><div class="card-body"><h3>${esc(person.label)}</h3><p class="subtext">${person.appearances} recorded track${person.appearances === 1 ? '' : 's'}</p><div class="spacer"></div><span class="btn small">Explore observations →</span></div></a>`).join('')}</div>`) +
  '<div class="notice">A person group organizes observations; it does not establish a name. New track IDs may belong to a previously seen person. Review matches before treating observations as one history.</div>';
}
async function personDetail(id) {
  const result = await api(`/api/people/${id}`);
  if (location.hash !== `#people/${id}`) return;
  const dated = result.observations.filter(row => row.recorded_at).sort((a,b) => Date.parse(a.first_observed) - Date.parse(b.first_observed));
  const undated = result.observations.filter(row => !row.recorded_at);
  const last = [...dated].sort((a,b) => Date.parse(b.last_observed) - Date.parse(a.last_observed))[0];
  const timeline = rows => rows.map(row => `<div class="timeline-row"><div class="panel"><img class="person-crop" src="${row.thumbnail_url}" alt="Person observation"><div class="track-info"><h3>${esc(row.location_label || 'Location unassigned')} · ${esc(row.camera_label || 'Unknown view')}</h3><p>${esc(row.first_observed)} → ${esc(row.last_observed)}</p><p>${esc(row.filename)} · person ${badge(row.match_status)} · view ${badge(row.location_status)}</p></div><div class="actions"><button class="btn small" data-action="open-source" data-id="${row.recording_id}" data-offset="${row.first_seen}">Open source ↗</button><button class="btn small" data-action="split" data-id="${row.id}">Split group</button></div></div></div>`).join('');
  const personLabel = state.people.find(person => person.id === id)?.label || id;
  const captured = `<section class="section"><div class="section-label"><h2>Captured appearances · ${result.observations.length} track(s)</h2>${result.observations.length ? `<button class="btn primary" data-action="search-crop" data-id="${result.observations[0].id}">Find this person in other recordings</button>` : ''}</div><div class="cards">${result.observations.map(row => `<article class="panel"><img class="appearance-capture" data-action="inspect-crop" data-id="${row.id}" src="${row.thumbnail_url}" alt="Captured appearance of ${esc(personLabel)}"><div class="card-body"><h3>${esc(row.location_label || 'Location unassigned')}</h3><p class="subtext">${esc(row.camera_label || 'Unknown camera')} · ${esc(row.filename)}</p><p class="subtext">${esc(row.first_observed)} → ${esc(row.last_observed)}</p><p class="subtext">Capture at ${offset(row.thumbnail_offset || row.first_seen)} &middot; ${esc(row.quality_status || "not checked")}</p><button type="button" class="btn small" data-action="inspect-crop" data-id="${row.id}">Original / enhanced clarity</button><div class="spacer"></div>${badge(row.match_status)} <a class="btn small" href="/api/recordings/${row.recording_id}/frame?at=${row.first_seen}" download="appearance.jpg">Save captured frame ↓</a></div></article>`).join('')}</div></section><div id="similar-appearance-results" class="section" aria-live="polite"></div>`;
  main.innerHTML = heading(esc(personLabel), 'Captured person images with their observed recordings, locations, and times.', `<div class="actions"><button class="btn primary" data-action="tracked-video" data-id="${id}">Create tracked video</button><a class="btn" href="/api/people/${id}/export">↓ Export CSV</a></div>`) + '<section id="tracked-video-output" class="section" aria-live="polite"></section>' + captured +
  (last ? `<div class="notice">Latest dated observation: <strong>${esc(last.location_label || 'Unknown location')}</strong> · ${esc(last.last_observed)} · ${esc(last.match_status)} person association / ${esc(last.location_status)} view</div>` : '') +
  (undated.length ? '<div class="notice warning">Some recordings have no known date. Those observations cannot be ordered globally or establish the latest location.</div>' : '') +
  (dated.length ? `<h2>Dated observations</h2>${timeline(dated)}` : '') +
  (undated.length ? `<h2 class="section">Recording offsets · dates unknown</h2>${timeline(undated)}` : '') +
  (!result.observations.length ? empty('No observations in this group', 'A correction may have moved these tracks to another group.') : '');
  if(result.videos?.length) await showTrackedVideo(result.videos[0].id);
}
async function showTrackedVideo(exportId){
  const panel=document.querySelector('#tracked-video-output');if(!panel)return;
  const result=await api(`/api/exports/${exportId}`);if(!panel.isConnected)return;
  if(result.status==='complete'){
    panel.innerHTML=`<div class="panel panel-pad"><h2>Tracked observation video</h2><p class="subtext">Associated appearances only, with person boxes, locations, cameras, and source times. Unknown dates are not invented. Audio is omitted.</p><video controls preload="metadata" src="${result.media_url}"></video><a class="btn" href="${result.media_url}" download="tracked-appearances.mp4">Download tracked video</a></div>`;
  }else if(['failed','interrupted'].includes(result.status))panel.innerHTML=`<div class="notice error">${esc(result.message)}</div>`;
  else{panel.innerHTML=`<div class="panel panel-pad"><h2>Creating tracked video…</h2><p class="subtext">${esc(result.message || 'Queued')}</p><div class="progress"><div style="width:${Math.round(result.progress*100)}%"></div></div></div>`;poll=setTimeout(()=>showTrackedVideo(exportId).catch(error=>toast(error.message,true)),1800);}
}
function reviewsPage() {
  const ready=state.reviews.filter(track=>track.candidates.length);
  const unresolved=state.reviews.filter(track=>!track.candidates.length);
  main.innerHTML=heading('Review uncertain connections.', 'Strong, clear-face matches reuse a shared person ID automatically. Only ambiguous candidates need a decision.')+
    `<div class="notice">Short fragments and tiny object detections are filtered before IDs are assigned. No face evidence means unresolved, not a confirmed new person.</div>`+
    (ready.length ? ready.map(track=>`<section class="panel review-card"><h2>${esc(track.label || track.person_id)} &middot; ${esc(track.filename)}</h2><div class="review-comparison"><img src="${track.thumbnail_url}" alt="New appearance"><div class="track-info"><p class="subtext">Observed at ${offset(track.first_seen)} to ${offset(track.last_seen)}</p>${track.candidates.map(candidate=>`<div class="candidate"><img src="${candidate.thumbnail_url}" alt="Candidate appearance"><div class="track-info"><h3>${esc(candidate.label)}</h3><p>Face cosine similarity ${candidate.score.toFixed(2)}</p></div><div class="actions"><button class="btn small primary" data-action="accept" data-id="${track.id}" data-target="${candidate.target_person_id}">Same person</button><button class="btn small" data-action="reject" data-id="${track.id}" data-target="${candidate.id}">Different person</button></div></div>`).join('')}<button class="btn small" data-action="view-appearances" data-id="${track.person_id}">Inspect captured evidence</button></div></div></section>`).join('') : `<div class="panel panel-pad">${empty('No ambiguous face connections to review', 'Confirmed associations and strong automatic matches are already reflected in person histories.', '?')}</div>`)+
    (unresolved.length ? `<details class="section"><summary>${unresolved.length} track(s) lack a supported returning-person match</summary><div class="notice warning">Some faces are too small, blurred, missing, or not similar enough to existing evidence. These observations remain provisional. Better footage may resolve them; clothing color is not used to guess.</div><div class="panel">${unresolved.map(track=>`<div class="track-row"><img class="person-crop" src="${track.thumbnail_url}" alt="Unresolved observation"><div class="track-info"><h3>${esc(track.label || track.person_id)}</h3><p>${esc(track.filename)} &middot; ${offset(track.first_seen)} to ${offset(track.last_seen)}</p><p>Evidence: ${esc(track.quality_status || 'not checked')}</p></div><button class="btn small" data-action="view-appearances" data-id="${track.person_id}">View captures</button><button class="btn small" data-action="manual-match" data-id="${track.id}" data-current="${track.person_id}">Correct ID manually</button></div>`).join('')}</div></details>`:'');
}
function searchMatches(rows, photo = false) {
  if (!rows.length) return empty('No matching observations found', photo ? 'No supported face match. The recording may contain a different person or lack a clear enough face. No result does not prove absence.' : 'Check the ID, change the location filter, or analyze more recordings.');
  const groups = new Set(rows.map(row => row.person_id)).size;
  return `<div class="section-label"><h2>${rows.length} observation${rows.length === 1 ? '' : 's'} · ${groups} person group${groups === 1 ? '' : 's'}</h2><span class="tag">${photo ? 'POSSIBLE APPEARANCES' : 'SAVED OBSERVATIONS'}</span></div><div class="panel">${rows.map(row => `<div class="track-row"><img class="person-crop" src="${row.thumbnail_url}" alt="Recorded person appearance"><div class="track-info"><h3><a href="#people/${row.person_id}">${esc(row.label)}</a> · ${esc(row.location_label || 'Location unassigned')}</h3><p>${esc(row.camera_label || 'Unknown view')} · ${esc(row.first_observed)} → ${esc(row.last_observed)}</p><p>${esc(row.filename)} · person ${badge(row.match_status)} · view ${badge(row.location_status)}${photo ? ` · face cosine similarity ${row.similarity.toFixed(2)}` : ''}</p></div><div class="actions"><button class="btn small" data-action="open-source" data-id="${row.recording_id}" data-offset="${row.first_seen}">Check video ↗</button><a class="btn small" href="#people/${row.person_id}">Full history</a></div></div>`).join('')}</div>`;
}
async function waitForRecording(id,form){
  while(form.isConnected){
    const row=await api(`/api/recordings/${id}`);
    form.querySelector('.form-status').textContent=`Analyzing camera video: ${Math.round(row.progress*100)}% - ${row.message}`;
    if(row.status==='complete')return;
    if(['failed','interrupted'].includes(row.status))throw new Error(row.message || 'Video analysis did not finish.');
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
  throw new Error('Search stopped after leaving this screen. Video processing continues in Recordings.');
}
function searchPage(){
  main.innerHTML=heading('Find a person in camera videos.','Give a clear photo, choose a recording, and find matching captures with camera, location, and time.')+
  `<section class="panel panel-pad"><form id="photo-search-form"><div class="dashboard-grid"><div><h2>1. Give the person photo</h2><p class="subtext">Use a clear, single-person face photo. Matching runs locally.</p><label class="dropzone" for="person-photo"><span class="drop-icon">?</span><strong id="person-photo-name">Choose person photo</strong><p>JPG, PNG, WebP - up to 10 MB</p><input id="person-photo" type="file" name="file" accept="image/jpeg,image/png,image/webp" required></label><img id="query-photo-preview" class="query-photo hidden" alt="Your search photo"></div><div><h2>2. Choose a camera recording</h2><label class="field">Saved recordings<select name="recording_id"><option value="">Choose a recording</option><option value="all">Search all analyzed camera recordings</option>${state.recordings.map(row=>`<option value="${row.id}">${esc(row.filename)} - ${esc(row.location_label || 'location pending')}</option>`).join('')}</select></label><div class="spacer"></div><label class="field">Or upload a new video to check<input id="search-video-file" type="file" name="new_video" accept="video/*,.avi,.mkv" style="position:static;width:100%;height:auto;opacity:1"></label><p class="subtext">A new video is analyzed automatically before the photo search. Camera labels are reused from saved reference views.</p><details><summary>New video's recording time (optional)</summary><div class="form-grid"><label class="field">Start time<input type="datetime-local" name="video_start" step="1"></label><label class="field">UTC offset<select name="utc_offset"><option>+05:00</option><option>+00:00</option><option>+05:30</option></select></label></div></details><div class="spacer"></div><button class="btn primary full" type="submit">Find this person</button><p class="form-status" role="status"></p></div></div></form></section>
  <details class="section"><summary>Already have a person ID? Search it here</summary><form id="id-search-form"><div class="filter-bar"><input class="search" name="q" placeholder="Person 0001 or saved ID" aria-label="Person ID" required><button class="btn" type="submit">Find by ID</button></div><p class="form-status"></p></form></details><div class="notice">Matches include captured images, camera/location, and source time. Missing or blurred faces return insufficient evidence rather than a clothing-color guess. Use Full history on a result to see its camera timeline or create a tracked video.</div><section class="section" id="person-search-results" aria-live="polite">${empty('Your results will appear here','Upload the person photo and choose the camera video to check.','?')}</section>`;
  let previewUrl=null;
  document.querySelector('#person-photo').addEventListener('change',event=>{
    const file=event.target.files[0];document.querySelector('#person-photo-name').textContent=file?.name || 'Choose person photo';
    if(previewUrl)URL.revokeObjectURL(previewUrl);
    const preview=document.querySelector('#query-photo-preview');preview.classList.toggle('hidden',!file);
    if(file){previewUrl=URL.createObjectURL(file);preview.src=previewUrl;}
  });
  document.querySelector('#photo-search-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.target;
    await submitForm(form,async data=>{
      const video=form.querySelector('#search-video-file').files[0];let recordingId=data.get('recording_id');
      if(video){
        const upload=new FormData();upload.set('file',video);
        if(data.get('video_start')){const start=data.get('video_start');upload.set('recorded_at',start+(start.length===16?':00':'')+data.get('utc_offset'));}
        form.querySelector('.form-status').textContent='Saving the new camera video...';
        const uploaded=await api('/api/recordings',{method:'POST',body:upload});recordingId=uploaded.id;
      }
      if(!recordingId)throw new Error('Choose a recording or upload a new camera video.');
      if(recordingId!=='all')await waitForRecording(recordingId,form);
      data.delete('new_video');data.delete('video_start');data.delete('utc_offset');
      if(recordingId==='all')data.delete('recording_id');else data.set('recording_id',recordingId);
      form.querySelector('.form-status').textContent='Comparing clear face evidence...';
      const result=await api('/api/search/photo',{method:'POST',body:data});
      document.querySelector('#person-search-results').innerHTML=searchMatches(result.matches,true);
      form.querySelector('.form-status').textContent=result.matches.length ? `${result.matches.length} matching observation(s) found. Check the captured images below.` : 'No supported match in the selected recording(s).';
    },'Checking your search...');
  });
  document.querySelector('#id-search-form').addEventListener('submit',async event=>{
    event.preventDefault();await submitForm(event.target,async data=>{
      const result=await api('/api/search/people?'+new URLSearchParams({q:data.get('q')}));
      document.querySelector('#person-search-results').innerHTML=searchMatches(result.matches);
      event.target.querySelector('.form-status').textContent=`${result.matches.length} saved observation(s).`;
    },'Finding the person history...');
  });
}
function agentPanels(result) {
  return `<div class="section-label"><h2>Automation tasks</h2><button class="btn small" data-action="refresh-agents">↻ Refresh</button></div><div class="panel">${result.runs.length ? result.runs.map(run => `<div class="track-row"><span class="step-no">✧</span><div class="track-info"><h3>${run.kind === "evidence_quality" ? "Evidence quality and face check" : "Location recheck"} ${badge(run.status)}</h3><p>${esc(run.message)}</p><p>${esc(run.created_at)} UTC · ${esc(run.id)}</p></div></div>`).join('') : empty('No reference rechecks yet', 'Saving a new reference can trigger an automatic check of unresolved recordings.')}</div>
  <section class="section"><h2>Decision and activity log</h2><p class="subtext">Automatic actions and reviewer decisions, with their recorded evidence.</p><div class="panel table-wrap"><table><thead><tr><th>Time (UTC)</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>${result.activity.map(item => `<tr><td>${esc(item.created_at)}</td><td>${esc(item.action.replaceAll('_',' '))}</td><td>${esc(item.target)}</td><td class="audit-detail">${esc(item.detail)}</td></tr>`).join('') || '<tr><td colspan="4">No actions recorded yet.</td></tr>'}</tbody></table></div></section>`;
}
async function refreshAgents() {
  const result = await api('/api/agents');
  if (location.hash !== '#agents') return;
  const panel = document.querySelector('#agent-panels');
  if (panel) panel.innerHTML = agentPanels(result);
  if (result.runs.some(row => ['running','queued'].includes(row.status))) poll = setTimeout(() => refreshAgents().catch(error => toast(error.message,true)),2000);
}
async function agentsPage() {
  const result = await api('/api/agents');
  if (location.hash !== '#agents') return;
  main.innerHTML = heading('Let the workflow keep moving.', 'Local automation with visible progress, saved memory, and reviewable decisions.') +
  `<div class="metrics">${[['Unresolved views',result.attention.unassigned_locations],['Tracks to review',result.attention.provisional_tracks],['Failed / interrupted jobs',result.attention.failed_jobs],['Active video jobs',state.overview.active_jobs]].map(([label,value]) => `<div class="metric"><span class="metric-label">${label}</span><div class="metric-value">${value}</div></div>`).join('')}</div><div class="dashboard-grid"><section class="panel panel-pad"><h2>Automatic workflow</h2>${[['1','Remember','Save labeled reference views and use them on future uploads.'],['2','Analyze','An upload queues location recognition, pedestrian detection, tracking, and appearance suggestions.'],['3','Revisit','New references can resolve old unknown views without rerunning person tracking.'],['4','Escalate','Uncertain views and person matches stay visible for human review.']].map(([num,title,description]) => `<div class="step"><span class="step-no">${num}</span><div><h3>${title}</h3><p>${description}</p></div></div>`).join('')}</section><section class="panel panel-pad"><h2>Automation settings</h2><form id="agent-settings"><label class="check-row"><input type="checkbox" name="auto_recheck" ${result.settings.auto_recheck ? 'checked' : ''}><span><strong>Recheck unresolved locations</strong><small>When a reference is added, compare it with previously unassigned completed recordings.</small></span></label><label class="check-row"><input type="checkbox" name="auto_resume" ${result.settings.auto_resume ? 'checked' : ''}><span><strong>Resume interrupted analysis</strong><small>After a server restart, retry incomplete jobs once if they have no saved track results.</small></span></label><button class="btn primary" type="submit">Save automation settings</button><p class="form-status" role="status"></p></form><div class="spacer"></div><button class="btn full" data-action="agent-recheck">Recheck unresolved locations now</button><div class="spacer"></div><button type="button" class="btn full" data-action="quality-refresh">Refresh sharp crops + face evidence</button></section></div><div class="notice">This local workflow controller includes location, detection, and evidence-quality checks. It automates processing and reference rechecks. It never invents locations, assigns names from a photo, or automatically confirms returning-person associations.</div><section class="section" id="agent-panels">${agentPanels(result)}</section>`;
  document.querySelector('#agent-settings').addEventListener('submit',async event => {
    event.preventDefault();
    await submitForm(event.target,async data => {
      await api('/api/agents/settings',jsonOptions('PATCH',{auto_recheck:data.has('auto_recheck'),auto_resume:data.has('auto_resume')}));
      event.target.querySelector('.form-status').textContent='Settings saved for future sessions.';
      await refreshAgents();
    },'Saving settings…');
  });
  if (result.runs.some(row => ['running','queued'].includes(row.status))) poll = setTimeout(() => refreshAgents().catch(error => toast(error.message,true)),2000);
}
function modal(title, contents) {
  document.querySelector('#modal-title').textContent = title;
  document.querySelector('#modal-body').innerHTML = contents;
  dialog.showModal();
}
function referenceDialog(locationId) {
  const saved = state.locations.find(row => row.id === locationId);
  modal(saved ? 'Add another reference' : 'Register a location', `<form id="reference-form"><p class="subtext">Save a viewpoint once so future uploads can recognize it automatically.</p><div class="form-grid"><label class="field">Location name<input name="label" placeholder="Main entrance" value="${esc(saved?.label || '')}" maxlength="100" required ${saved ? 'readonly' : ''}></label><label class="field">Camera / view label<input name="camera_label" placeholder="CAM-01" value="${esc(saved?.camera_label || '')}" maxlength="80" required ${saved ? 'readonly' : ''}></label></div>${saved ? `<input type="hidden" name="location_id" value="${saved.id}">` : ''}<label class="dropzone" for="reference-file"><span class="drop-icon">⌖</span><strong id="reference-name">Choose a reference video</strong><p>Use clear footage with a stable background.</p><input id="reference-file" type="file" name="file" accept="video/*,.avi,.mkv" required></label><button type="submit" class="btn primary full">Save reference view →</button><p class="form-status" role="status"></p></form>`);
  document.querySelector('#reference-file').addEventListener('change', event => document.querySelector('#reference-name').textContent = event.target.files[0]?.name || 'Choose a reference video');
  document.querySelector('#reference-form').addEventListener('submit', async event => {
    event.preventDefault();
    await submitForm(event.target, async data => {
      await api('/api/references', {method:'POST', body:data});
      dialog.close(); toast('Reference saved. This view is ready for future uploads.'); await load();
    }, 'Sampling reference frames and saving background features…');
  });
}
async function submitForm(form, callback, message) {
  const button = form.querySelector('button[type=submit]');
  const status = form.querySelector('.form-status');
  button.disabled = true; status.textContent = message;
  try { await callback(new FormData(form)); }
  catch (error) {status.textContent = error.message; toast(error.message, true);}
  finally {button.disabled = false;}
}
function bindUpload() {
  const form = document.querySelector('#upload-form');
  if (!form) return;
  const input = form.querySelector('#recording-file');
  const zone = form.querySelector('.dropzone');
  input.addEventListener('change', () => document.querySelector('#upload-name').textContent = input.files[0]?.name || 'Drop your video here');
  for (const name of ['dragenter','dragover']) zone.addEventListener(name, event => {event.preventDefault();zone.classList.add('drag');});
  for (const name of ['dragleave','drop']) zone.addEventListener(name, event => {event.preventDefault();zone.classList.remove('drag');});
  zone.addEventListener('drop', event => {
    if (event.dataTransfer.files.length) {
      const transfer = new DataTransfer(); transfer.items.add(event.dataTransfer.files[0]); input.files = transfer.files;
      input.dispatchEvent(new Event('change'));
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const file = input.files[0];
    if (!file || file.size > 250 * 1024 * 1024) return toast('Choose a non-empty video under 250 MB.', true);
    await submitForm(form, async data => {
      const start = data.get('start_time');
      if (start) data.set('recorded_at', start + (start.length === 16 ? ':00' : '') + data.get('utc_offset'));
      data.delete('start_time'); data.delete('utc_offset');
      const result = await api('/api/recordings', {method:'POST', body:data});
      if (dialog.open) dialog.close();
      toast(result.duplicate ? 'This file is already saved. Opening its results.' : 'Recording queued for analysis.');
      goTo(`recordings/${result.id}`);
    }, 'Uploading and checking video…');
  });
}
async function load() {
  clearTimeout(poll);
  const [overview, locations, recordings, people, reviews] = await Promise.all(['overview','locations','recordings','people','reviews'].map(name => api(`/api/${name}`)));
  Object.assign(state, {overview,locations,recordings,people,reviews});
  document.querySelector('#review-count').textContent = overview.reviews;
  document.querySelector('#connection').textContent = 'Local connection';
  await render();
}
async function render() {
  clearTimeout(poll);
  const [rawPage, id] = location.hash.replace('#','').split('/');
  const page = pageName[rawPage] ? rawPage : 'overview';
  document.querySelector('#breadcrumb').textContent = pageName[page];
  document.querySelectorAll('nav a').forEach(link => {link.classList.toggle('active', link.dataset.page === page);link.setAttribute('aria-current',link.dataset.page === page ? 'page' : 'false');});
  main.setAttribute('aria-busy','false');
  if (page === 'recordings' && id) return recordingDetail(encodeURIComponent(id));
  if (page === 'people' && id) return personDetail(encodeURIComponent(id));
  return ({overview,locations:locationsPage,recordings:recordingsPage,people:peoplePage,search:searchPage,reviews:reviewsPage,agents:agentsPage}[page])();
}
async function reviewAction(id, payload) {
  await api(`/api/tracks/${id}/review`, jsonOptions('POST',payload));
  toast('Decision saved. Observation history updated.'); await load();
}
function goTo(hash){history.pushState(null,'',`#${hash.replace(/^#/,'')}`);load().catch(error=>toast(error.message,true));}
document.addEventListener('click', async event => {
  const link=event.target.closest('a[href^="#"]');
  if(link){event.preventDefault();goTo(link.getAttribute('href'));return;}
  const button = event.target.closest('[data-action]');
  if (!button) return;
  event.preventDefault();
  const {action,id,target,current} = button.dataset;
  try {
    if (action === 'add-location') referenceDialog();
    if (action === 'add-reference') referenceDialog(id);
    if (action === 'upload') {if(dialog.open)dialog.close();goTo('overview');}
    if (action === 'view-appearances') goTo(`people/${id}`);
    if (action === 'tracked-video') {const result=await api(`/api/people/${id}/tracked-video`,{method:'POST'});await showTrackedVideo(result.id);}
    if (action === 'reanalyze') {await api(`/api/recordings/${id}/reanalyze`,{method:'POST'});await load();}
    if (action === 'quality-refresh') {await api('/api/agents/quality-refresh',{method:'POST'});toast('Evidence quality refresh queued.');clearTimeout(poll);await refreshAgents();}
    if (action === 'inspect-crop') {
      modal('Captured evidence: original and enhanced',`<p class="subtext">The original stays unchanged. Denoising, contrast, and mild sharpening can improve display, but cannot recover missing facial detail. Matching uses original evidence only.</p><div class="capture-comparison"><figure><img class="evidence-full" src="/api/tracks/${id}/thumbnail" alt="Original crop"><figcaption>Original source crop</figcaption></figure><figure><img class="evidence-full" src="/api/tracks/${id}/thumbnail?enhance=true" alt="Enhanced preview"><figcaption>Display filters only</figcaption></figure></div>`);
    }
    if (action === 'teach-view') {
      modal('Teach this angle to a saved location',`<p class="subtext">Your location labels are saved. Choose where this recording was made and save it as an additional reference angle. Later recordings of this angle can be recognized automatically.</p><form id="teach-view-form"><label class="field">Saved location<select name="location_id">${state.locations.map(row=>`<option value="${row.id}">${esc(row.label)} &middot; ${esc(row.camera_label)}</option>`).join('')}</select></label><button class="btn primary" type="submit" ${state.locations.length?'':'disabled'}>Save this reference angle</button><p class="form-status" role="status"></p></form>`);
      document.querySelector('#teach-view-form').addEventListener('submit',async event=>{
        event.preventDefault();await submitForm(event.target,async data=>{await api(`/api/recordings/${id}/teach-location`,jsonOptions('POST',{location_id:data.get('location_id')}));dialog.close();toast('New angle saved. Unknown recordings will be rechecked.');await load();},'Saving this angle and its location…');
      });
    }
    if (action === 'search-crop') {
      button.disabled=true;
      try{
        const response=await fetch(`/api/tracks/${id}/thumbnail`);
        if(!response.ok)throw new Error('The person crop is unavailable.');
        const data=new FormData();data.append('file',await response.blob(),'person-appearance.jpg');
        const result=await api('/api/search/photo',{method:'POST',body:data});
        const panel=document.querySelector('#similar-appearance-results');
        if(panel){panel.innerHTML='<div class="notice warning">Possible appearances ranked by face cosine similarity. Review these images before associating people.</div>'+searchMatches(result.matches,true);panel.scrollIntoView({behavior:'smooth',block:'start'});}
      }finally{button.disabled=false;}
    }
    if (action === 'refresh') await load();
    if (action === 'refresh-agents') {clearTimeout(poll);await refreshAgents();}
    if (action === 'agent-recheck') {await api('/api/agents/recheck',{method:'POST'});toast('Location recheck queued.');clearTimeout(poll);await refreshAgents();}
    if (action === 'seek') {const video = document.querySelector('#source-video');if (video) {video.currentTime = Number(button.dataset.offset);video.play().catch(() => {});}}
    if (action === 'open-source') {sessionStorage.setItem('seek-recording',id);sessionStorage.setItem('seek-time',button.dataset.offset);goTo(`recordings/${id}`);}
    if (action === 'retry') {await api(`/api/recordings/${id}/retry`,{method:'POST'});await load();}
    if (action === 'keep') await reviewAction(id,{action:'keep'});
    if (action === 'accept') await reviewAction(id,{action:'accept',person_id:target});
    if (action === 'reject') await reviewAction(id,{action:'reject',candidate_id:target});
    if (action === 'split' && confirm('Move this track into a new provisional person group? The original observation will be preserved.')) await reviewAction(id,{action:'split'});
    if (action === 'delete-recording' && confirm('Delete this recording, source video, thumbnails, and dependent observations?')) {await api(`/api/recordings/${id}`,{method:'DELETE'});goTo('recordings');toast('Recording deleted.');}
    if (action === 'rename-location') {
      const label = prompt('Location name', locationName(id));
      if (label) {await api(`/api/locations/${id}`,jsonOptions('PATCH',{label}));await load();}
    }
    if (action === 'correct-location') {
      modal('Review the recording location', `<p class="subtext">Confirm a saved location only after checking the footage.</p><div class="spacer"></div>${state.locations.length ? `<form id="assign-location"><label class="field">Saved view<select name="location_id">${state.locations.map(row => `<option value="${row.id}">${esc(row.label)} · ${esc(row.camera_label)}</option>`).join('')}</select></label><button class="btn primary" type="submit">Confirm location</button><p class="form-status"></p></form>` : '<p class="subtext">No reference views are registered.</p>'}<div class="spacer"></div><a class="btn small" href="#locations" id="go-locations">Register a new view →</a>`);
      document.querySelector('#go-locations').onclick = () => dialog.close();
      document.querySelector('#assign-location')?.addEventListener('submit', async event => {event.preventDefault();await submitForm(event.target,async data => {await api(`/api/recordings/${id}/location`,jsonOptions('PATCH',{location_id:data.get('location_id')}));dialog.close();await load();},'Saving correction…');});
    }
    if (action === 'manual-match') {
      const people = state.people.filter(row => row.id !== current);
      modal('Choose an existing person group', people.length ? `<p class="subtext">Check source footage before confirming a match.</p><form id="manual-match"><label class="field">Person group<select name="person_id">${people.map(row => `<option value="${row.id}">${esc(row.label)} · ${row.appearances} track(s)</option>`).join('')}</select></label><button class="btn primary" type="submit">Confirm association</button><p class="form-status"></p></form>` : '<p class="subtext">No other person groups exist yet.</p>');
      document.querySelector('#manual-match')?.addEventListener('submit',async event => {event.preventDefault();await submitForm(event.target,async data => {await reviewAction(id,{action:'accept',person_id:data.get('person_id')});dialog.close();},'Saving association…');});
    }
  } catch(error) {toast(error.message,true);}
});
document.querySelector('#close-modal').onclick = () => dialog.close();
dialog.addEventListener('close',()=>document.querySelector('#modal-body').replaceChildren());
document.querySelector('#about').onclick = () => modal('About this build', '<p class="subtext">SceneTrace runs locally with a custom browser interface, a Python API, and a SQLite database.</p><div class="notice">The current baseline uses ORB geometric scene matching, YOLOX person-only detection, and motion-assisted overlap tracking. Quality-gated SFace descriptors generate face candidates for review. Clothing-only identity matching is disabled.</div><p class="subtext">Accuracy needs evaluation on your recordings. Stronger re-identification, scene segmentation, and live webcam sessions are later milestones. Only upload footage you are permitted to process.</p>');
window.addEventListener('hashchange', () => load().catch(error => toast(error.message,true)));
window.addEventListener('popstate', () => load().catch(error => toast(error.message,true)));
load().catch(error => {document.querySelector('#connection').textContent='Connection unavailable';main.innerHTML = heading('The workspace is unavailable.',esc(error.message)) + '<p class="subtext">Start the local server with <code>.venv\\Scripts\\python.exe app.py</code> and reload this page.</p>';});
