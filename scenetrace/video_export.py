"""Create local H.264 highlight videos from a person's actual observation intervals."""
from datetime import datetime
from pathlib import Path
import json
import subprocess
import tempfile

import cv2
import imageio_ffmpeg
import numpy as np

from . import store, service


def queue(person_id):
    pending=store.query("SELECT id FROM exports WHERE person_id=? AND status IN ('queued','processing')",(person_id,))
    if pending:
        return pending[0]["id"]
    rows=store.query("SELECT DISTINCT recording_id FROM tracks WHERE person_id=?",(person_id,))
    if not rows:
        raise ValueError("No associated observations exist for this person group.")
    export_id=store.new_id("export")
    path=store.DATA/'exports'/f'{export_id}.mp4'
    with store.connect() as db:
        db.execute("INSERT INTO exports(id,person_id,status,path) VALUES(?,?,'queued',?)",(export_id,person_id,str(path)))
        db.executemany("INSERT INTO export_sources VALUES(?,?)",[(export_id,row["recording_id"]) for row in rows])
    service.EXECUTOR.submit(build,export_id)
    return export_id


def build(export_id):
    process=None
    temporary=None
    try:
        export=store.query("SELECT * FROM exports WHERE id=?",(export_id,))[0]
        rows=store.query("""SELECT t.*,p.label,r.path,r.filename,r.duration,r.recorded_at,l.label AS location_label,l.camera_label
            FROM tracks t JOIN people p ON p.id=t.person_id JOIN recordings r ON r.id=t.recording_id
            LEFT JOIN locations l ON l.id=r.location_id WHERE t.person_id=?""",(export["person_id"],))
        rows.sort(key=lambda row:(0,datetime.fromisoformat(row['recorded_at']).timestamp()+row['first_seen']) if row['recorded_at'] else (1,row['recording_id'],row['first_seen']))
        segments=[]
        for row in rows:
            start=max(0,row['first_seen']-.15)
            end=min(row['duration'],row['last_seen']+.15)
            if end>start:
                segments.append((row,start,end))
        total=sum(end-start for _,start,end in segments)
        if not total or total>600:
            raise ValueError("Tracked-video export requires observation intervals totaling between 0 and 600 seconds.")
        store.execute("UPDATE exports SET status='processing',message='Rendering captured observation intervals' WHERE id=?",(export_id,))
        output=Path(export['path']);temporary=output.with_suffix('.part.mp4')
        command=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','bgr24',
            '-s','960x540','-r','12','-i','-','-an','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)]
        written=0;expected=max(1,int(total*12))
        with tempfile.TemporaryFile(dir=store.DATA/'exports') as errors:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for row,start,end in segments:
                detections=store.query("SELECT * FROM detections WHERE recording_id=? AND local_id=? ORDER BY offset",(row['recording_id'],row['local_id']))
                cap=cv2.VideoCapture(row['path'])
                try:
                    for timestamp in np.arange(start,end,1/12):
                        cap.set(cv2.CAP_PROP_POS_MSEC,float(timestamp)*1000)
                        ok,frame=cap.read()
                        if not ok:continue
                        near=min(detections,key=lambda item:abs(item['offset']-timestamp)) if detections else None
                        if near and abs(near['offset']-timestamp)<.16:
                            x,y,w,h=json.loads(near['box']);height,width=frame.shape[:2]
                            x,y,w,h=int(x*width),int(y*height),int(w*width),int(h*height)
                            cv2.rectangle(frame,(x,y),(x+w,y+h),(95,240,130),3)
                            cv2.putText(frame,row['label'],(x,max(22,y-8)),cv2.FONT_HERSHEY_SIMPLEX,.7,(95,240,130),2)
                        scale=min(960/frame.shape[1],480/frame.shape[0]);resized=cv2.resize(frame,(int(frame.shape[1]*scale),int(frame.shape[0]*scale)))
                        canvas=np.full((540,960,3),22,np.uint8);x=(960-resized.shape[1])//2;y=60+(480-resized.shape[0])//2
                        canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
                        caption=f"{row['label']} | {row['location_label'] or 'Location unassigned'} | {row['camera_label'] or 'Unknown view'}"
                        time_label=service.observation_time(row['recorded_at'],float(timestamp))
                        cv2.putText(canvas,caption.encode('ascii','replace').decode(),(15,23),cv2.FONT_HERSHEY_SIMPLEX,.55,(215,240,225),1)
                        cv2.putText(canvas,f"{row['filename'][:60]} | {time_label}".encode('ascii','replace').decode(),(15,47),cv2.FONT_HERSHEY_SIMPLEX,.4,(165,185,175),1)
                        process.stdin.write(canvas.tobytes());written+=1
                        if written%12==0:
                            store.execute("UPDATE exports SET progress=?,message=? WHERE id=?",(min(.98,written/expected),f'Rendering frame {written}',export_id))
                finally:cap.release()
            process.stdin.close()
            code=process.wait(timeout=60)
            if code or not written:
                errors.seek(0)
                raise ValueError('Video encoder failed: '+errors.read(400).decode(errors='replace'))
        temporary.replace(output)
        with store.connect() as db:
            db.execute("UPDATE exports SET status='complete',progress=1,message=? WHERE id=?",(f'{written} frames; evidence excerpts only; no inferred route or audio',export_id))
            store.audit(db,'tracked_video_created',export_id,{'person_id':export['person_id'],'segments':len(segments),'frames':written})
    except Exception as error:
        if process and process.poll() is None:process.kill();process.wait()
        if temporary:temporary.unlink(missing_ok=True)
        store.execute("UPDATE exports SET status='failed',message=? WHERE id=?",(str(error)[:400],export_id))
