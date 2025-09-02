package main

import (
	"image"
	"image/color"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"math/rand"
	"sync"
	"time"

	"github.com/disintegration/imaging"
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/widget"
)

type Direction int

const (
    DirTopToBottom Direction = iota
    DirLeftToRight
    DirRightToLeft
    DirBottomToTop
)

type AppState struct {
    mu          sync.RWMutex
    direction   Direction
    bgImage     image.Image
    pigStickers []image.Image

    // rendering
    width  int
    height int

    // pigs and animation
    pigs        []*Pig
    running     bool
    stopCh      chan struct{}
    frameTicker *time.Ticker
}

type Pig struct {
    x, y   float64
    vx, vy float64
    sprite image.Image
    w, h   int
}

func main() {
    a := app.New()
    w := a.NewWindow("Pig Stream Generator")
    w.Resize(fyne.NewSize(1024, 640))

    state := &AppState{direction: DirLeftToRight, width: 960, height: 540}

    // Placeholder video canvas: start with a blank image
    nrgba := imaging.New(state.width, state.height, color.NRGBA{R: 30, G: 30, B: 30, A: 255})
    videoCanvas := canvas.NewImageFromImage(nrgba)
    videoCanvas.FillMode = canvas.ImageFillContain
    videoCanvas.SetMinSize(fyne.NewSize(float32(state.width), float32(state.height)))

    // Direction selector
    dirOptions := []string{"上到下", "左到右", "右到左", "下到上"}
    dirSelect := widget.NewSelect(dirOptions, func(value string) {
        state.mu.Lock()
        defer state.mu.Unlock()
        switch value {
        case "上到下":
            state.direction = DirTopToBottom
        case "左到右":
            state.direction = DirLeftToRight
        case "右到左":
            state.direction = DirRightToLeft
        case "下到上":
            state.direction = DirBottomToTop
        }
    })
    dirSelect.SetSelected(dirOptions[1])

    // Buttons
    btnSetBg := widget.NewButton("上传背景", func() {
        openImage(w, func(img image.Image, err error) {
            if err != nil || img == nil {
                return
            }
            state.mu.Lock()
            state.bgImage = img
            state.mu.Unlock()
            updateCanvasFrame(state, videoCanvas)
        })
    })
    btnAddSticker := widget.NewButton("添加猪只贴图", func() {
        openImage(w, func(img image.Image, err error) {
            if err != nil || img == nil {
                return
            }
            state.mu.Lock()
            state.pigStickers = append(state.pigStickers, img)
            state.mu.Unlock()
        })
    })
    btnStartSpawn := widget.NewButton("开始出猪", func() {
        state.mu.Lock()
        if state.running {
            state.mu.Unlock()
            return
        }
        if len(state.pigStickers) == 0 {
            state.mu.Unlock()
            dialog.ShowInformation("提示", "请先添加至少一张猪只贴图", w)
            return
        }
        state.running = true
        state.stopCh = make(chan struct{})
        state.mu.Unlock()

        go spawnLoop(state)
        go renderLoop(state, videoCanvas)
    })
    btnStartPush := widget.NewButton("开启推送", func() {
        // implemented later
    })

    ctrl := container.NewVBox(
        widget.NewLabel("方向配置"),
        dirSelect,
        container.NewGridWithColumns(2, btnSetBg, btnAddSticker),
        container.NewGridWithColumns(2, btnStartSpawn, btnStartPush),
    )

    content := container.NewBorder(ctrl, nil, nil, nil, container.NewCenter(videoCanvas))
    w.SetContent(content)

    // initial draw
    updateCanvasFrame(state, videoCanvas)

    w.ShowAndRun()
}

// removed fill helper; using imaging.New to allocate filled frames

// openImage shows a file-open dialog and decodes to image.Image
func openImage(w fyne.Window, cb func(image.Image, error)) {
    dlg := dialog.NewFileOpen(func(r fyne.URIReadCloser, err error) {
        if err != nil {
            cb(nil, err)
            return
        }
        if r == nil {
            cb(nil, nil)
            return
        }
        defer r.Close()
        img, _, decErr := image.Decode(r)
        cb(img, decErr)
    }, w)
    dlg.SetFilter(storage.NewExtensionFileFilter([]string{".png", ".jpg", ".jpeg", ".gif"}))
    dlg.Show()
}

// updateCanvasFrame composites background to target canvas size
func updateCanvasFrame(state *AppState, imgWidget *canvas.Image) {
    state.mu.RLock()
    bg := state.bgImage
    w := state.width
    h := state.height
    state.mu.RUnlock()

    frame := imaging.New(w, h, color.NRGBA{R: 30, G: 30, B: 30, A: 255})
    if bg != nil {
        fitted := imaging.Fill(bg, w, h, imaging.Center, imaging.Linear)
        frame = imaging.Paste(frame, fitted, image.Pt(0, 0))
    }
    imgWidget.Image = frame
    imgWidget.Refresh()
}

// removed drawImage helper; using imaging.Paste/Overlay for composition

// spawnLoop periodically spawns pigs outside the canvas and assigns velocities
func spawnLoop(state *AppState) {
    rand.Seed(time.Now().UnixNano())
    for {
        // random interval between 300-900ms
        wait := time.Duration(300+rand.Intn(600)) * time.Millisecond
        select {
        case <-time.After(wait):
            state.mu.Lock()
            if !state.running {
                state.mu.Unlock()
                return
            }
            if len(state.pigStickers) == 0 {
                state.mu.Unlock()
                continue
            }
            // pick sprite and scale to reasonable size (height ~ 120px)
            src := state.pigStickers[rand.Intn(len(state.pigStickers))]
            scaled := imaging.Resize(src, 0, 120, imaging.Linear)
            pig := &Pig{sprite: scaled, w: scaled.Bounds().Dx(), h: scaled.Bounds().Dy()}

            // spawn position and velocity based on direction
            switch state.direction {
            case DirTopToBottom:
                pig.x = float64(rand.Intn(state.width - pig.w))
                pig.y = float64(-pig.h)
                speed := 80 + rand.Float64()*120
                pig.vx = 0
                pig.vy = speed
            case DirBottomToTop:
                pig.x = float64(rand.Intn(state.width - pig.w))
                pig.y = float64(state.height + pig.h)
                speed := 80 + rand.Float64()*120
                pig.vx = 0
                pig.vy = -speed
            case DirLeftToRight:
                pig.x = float64(-pig.w)
                pig.y = float64(rand.Intn(state.height - pig.h))
                speed := 80 + rand.Float64()*120
                pig.vx = speed
                pig.vy = 0
            case DirRightToLeft:
                pig.x = float64(state.width + pig.w)
                pig.y = float64(rand.Intn(state.height - pig.h))
                speed := 80 + rand.Float64()*120
                pig.vx = -speed
                pig.vy = 0
            }
            state.pigs = append(state.pigs, pig)
            state.mu.Unlock()
        case <-state.stopCh:
            return
        }
    }
}

// renderLoop updates positions and renders the frame at ~30fps
func renderLoop(state *AppState, imgWidget *canvas.Image) {
    ticker := time.NewTicker(time.Second / 30)
    defer ticker.Stop()
    last := time.Now()
    for {
        select {
        case <-ticker.C:
            now := time.Now()
            dt := now.Sub(last).Seconds()
            last = now

            // update pig positions and cull
            state.mu.Lock()
            if !state.running {
                state.mu.Unlock()
                return
            }
            filtered := state.pigs[:0]
            for _, p := range state.pigs {
                p.x += p.vx * dt
                p.y += p.vy * dt
                if insideCanvas(p, state.width, state.height) {
                    filtered = append(filtered, p)
                }
            }
            state.pigs = filtered

            // compose frame
            frame := imaging.New(state.width, state.height, color.NRGBA{R: 30, G: 30, B: 30, A: 255})
            if state.bgImage != nil {
                fitted := imaging.Fill(state.bgImage, state.width, state.height, imaging.Center, imaging.Linear)
                frame = imaging.Paste(frame, fitted, image.Pt(0, 0))
            }
            for _, p := range state.pigs {
                px := int(p.x)
                py := int(p.y)
                // overlay with alpha
                frame = imaging.Overlay(frame, p.sprite, image.Pt(px, py), 1.0)
            }
            state.mu.Unlock()

            imgWidget.Image = frame
            imgWidget.Refresh()
        case <-state.stopCh:
            return
        }
    }
}

func insideCanvas(p *Pig, w, h int) bool {
    // If pig still intersects canvas rect
    if p.x+float64(p.w) < 0 || p.y+float64(p.h) < 0 {
        return false
    }
    if p.x > float64(w) || p.y > float64(h) {
        return false
    }
    return true
}

