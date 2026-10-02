import { useEffect, useRef, useState } from 'react'
import './App.css'

const API = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? '' : 'https://launchflow-ai.onrender.com')).replace(/\/$/, '')

function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function storeValue(key, value) {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('launchflow-storage-warning'))
    return false
  }
}

function parseStored(key, fallback) {
  try {
    const value = readStored(key)
    if (!value) return fallback
    const parsed = JSON.parse(value)
    if (fallback && typeof fallback === 'object' && !Array.isArray(fallback)) {
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return fallback
      return { ...fallback, ...parsed }
    }
    if (fallback === null && parsed !== null && (typeof parsed !== 'object' || Array.isArray(parsed))) return null
    return parsed
  } catch {
    return fallback
  }
}

const platforms = [
  { id: 'instagram', name: 'Instagram', icon: '◎' },
  { id: 'youtube', name: 'YouTube', icon: '▶' },
  { id: 'facebook', name: 'Facebook', icon: 'f' },
  { id: 'x', name: 'X', icon: '𝕏' },
  { id: 'whatsapp', name: 'WhatsApp', icon: '◉' },
]

const campaignAssets = {
  instagram: [
    { key: 'instagram', label: 'Instagram Post', dimensions: '1080 × 1350 • 4:5' },
    { key: 'instagram_story', label: 'Instagram Story / Reel', dimensions: '1080 × 1920 • 9:16' },
  ],
  youtube: [
    { key: 'youtube', label: 'YouTube Thumbnail', dimensions: '1280 × 720 • 16:9' },
    { key: 'youtube_shorts', label: 'YouTube Short', dimensions: '1080 × 1920 • 9:16' },
  ],
  facebook: [{ key: 'facebook', label: 'Facebook Post', dimensions: '1080 × 1080 • 1:1' }],
  x: [{ key: 'x', label: 'X Post', dimensions: '1600 × 900 • 16:9' }],
  whatsapp: [
    { key: 'whatsapp', label: 'WhatsApp Message', dimensions: '1080 × 1080 • 1:1' },
    { key: 'whatsapp_status', label: 'WhatsApp Status', dimensions: '1080 × 1920 • 9:16' },
  ],
}

const emptyCampaign = {
  platforms: {},
  campaign_brain: {},
}

const emptyForm = {
  productName: '',
  description: '',
  price: '',
  audience: '',
  usp: '',
  brandTone: 'friendly',
}

const toApiBrief = (form) => ({
  product_name: form.productName,
  description: form.description,
  price: form.price,
  audience: form.audience,
  usp: form.usp,
  brand_tone: form.brandTone,
})

function applyPlatformCopy(source, platform, generatedCopy) {
  const campaign = structuredClone(source || emptyCampaign)
  campaign.platforms ||= {}
  const platformData = campaign.platforms[platform] ||= {}
  const section = platform === 'youtube' ? 'short' : platform === 'whatsapp' ? 'message' : 'post'
  const current = platformData[section] || {}
  const textField = platform === 'x' ? 'text' : platform === 'whatsapp' ? 'text' : 'caption'
  platformData[section] = {
    ...current,
    [textField]: generatedCopy.text || '',
    cta: generatedCopy.cta || current.cta || '',
    ...(platform === 'instagram' && { hashtags: generatedCopy.hashtags || current.hashtags || [] }),
  }
  return campaign
}

function dataUrlToFile(dataUrl, filename = 'product-image.jpg') {
  if (!dataUrl || !dataUrl.startsWith('data:')) {
    return null
  }

  const [header, base64] = dataUrl.split(',')
  const mime =
    header.match(/data:(.*?);base64/)?.[1] ||
    'image/jpeg'

  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)

  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }

  return new File([bytes], filename, {
    type: mime,
  })
}

function App() {
  const generationId = useRef(0)
  const [activePlatform, setActivePlatform] =
    useState('instagram')

  const [form, setForm] = useState(() => parseStored('launchflow_form', emptyForm))

  const [imageFile, setImageFile] = useState(null)
  const [imagePreview, setImagePreview] =
    useState(null)

  const [campaign, setCampaign] =
    useState(() => parseStored('launchflow_campaign', emptyCampaign))

  const [platformImages, setPlatformImages] =
    useState(() => parseStored('launchflow_images', {}))

  const [platformImageVariants, setPlatformImageVariants] =
    useState(() => parseStored('launchflow_image_variants', {}))

  const [activeAssetKey, setActiveAssetKey] = useState('instagram')

  const [scriptIdeas, setScriptIdeas] =
    useState(() => parseStored('launchflow_scripts', {}))

  const [imageErrors, setImageErrors] =
    useState(() => parseStored('launchflow_image_errors', {}))

  const [quality, setQuality] =
    useState(() => parseStored('launchflow_quality', null))

  const [approved, setApproved] =
    useState(() => readStored('launchflow_approved') === 'true')

  const [approvalAcknowledged, setApprovalAcknowledged] =
    useState(false)

  const [imageNeedsReselect, setImageNeedsReselect] =
    useState(() => readStored('launchflow_image_pending') === 'true' || Boolean(readStored('launchflow_preview')))

  const [storageWarning, setStorageWarning] =
    useState(false)

  const apiAvailable = useRef(false)

  const [loading, setLoading] =
    useState(false)

  const [actionLoading, setActionLoading] =
    useState('')

  const [error, setError] =
    useState('')

  const [copyStatus, setCopyStatus] = useState('')

  const [generated, setGenerated] =
    useState(() => readStored('launchflow_generated') === 'true')

  // ---------------------------------------------------------
  // Restore campaign
  // ---------------------------------------------------------

  useEffect(() => {
    let alive = true
    const checkBackend = () => fetch(`${API}/api/health`)
      .then((response) => response.json().then((data) => ({ response, data })))
      .then(({ response, data }) => {
        if (alive) apiAvailable.current = Boolean(response.ok && data.ok)
      })
      .catch(() => { if (alive) apiAvailable.current = false })
    checkBackend()
    const timer = window.setInterval(checkBackend, 15000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    const showStorageWarning = () => setStorageWarning(true)
    window.addEventListener('launchflow-storage-warning', showStorageWarning)
    try { localStorage.removeItem('launchflow_preview') } catch {}
    return () => window.removeEventListener('launchflow-storage-warning', showStorageWarning)
  }, [])

  // ---------------------------------------------------------
  // Persistence
  // ---------------------------------------------------------

  useEffect(() => {
    storeValue('launchflow_form', JSON.stringify(form))
  }, [form])

  useEffect(() => {
    storeValue('launchflow_campaign', JSON.stringify(campaign))
  }, [campaign])

  useEffect(() => {
    storeValue('launchflow_images', JSON.stringify(platformImages))
  }, [platformImages])

  useEffect(() => {
    storeValue('launchflow_image_variants', JSON.stringify(platformImageVariants))
  }, [platformImageVariants])

  useEffect(() => {
    storeValue('launchflow_scripts', JSON.stringify(scriptIdeas))
  }, [scriptIdeas])

  useEffect(() => {
    storeValue('launchflow_image_errors', JSON.stringify(imageErrors))
  }, [imageErrors])

  useEffect(() => {
    storeValue('launchflow_quality', JSON.stringify(quality))
  }, [quality])

  useEffect(() => {
    storeValue('launchflow_approved', approved ? 'true' : 'false')
  }, [approved])

  useEffect(() => {
    storeValue('launchflow_generated', generated ? 'true' : 'false')
  }, [generated])

  // ---------------------------------------------------------
  // Form
  // ---------------------------------------------------------

  const handleChange = (event) => {
    const {
      name,
      value,
    } = event.target

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }))
    generationId.current += 1
    setLoading(false)
    setActionLoading('')
    setApproved(false)
    setApprovalAcknowledged(false)
    setGenerated(false)
    setQuality(null)
  }

  const handleImageChange = (event) => {
    const file =
      event.target.files?.[0]

    if (!file) return

    generationId.current += 1
    setLoading(false)
    setActionLoading('')
    const imageRequestId = generationId.current

    const restoringSourceForSavedCampaign = imageNeedsReselect && generated

    setImageFile(file)

    const reader =
      new FileReader()

    reader.onload = () => {
      if (imageRequestId !== generationId.current) return
      setImagePreview(
        reader.result,
      )
      setImageNeedsReselect(false)
      storeValue('launchflow_image_pending', 'true')
    }

    reader.readAsDataURL(file)

    if (!restoringSourceForSavedCampaign) {
      setPlatformImages({})
      setPlatformImageVariants({})
      setImageErrors({})
      setScriptIdeas({})
      setGenerated(false)
      setQuality(null)
    }
    setApproved(false)
    setApprovalAcknowledged(false)
  }

  const getImageFile = () => {
    if (imageFile) {
      return imageFile
    }

    return dataUrlToFile(
      imagePreview,
    )
  }

  const createFormData = () => {
    const formData =
      new FormData()

    formData.append(
      'product_name',
      form.productName,
    )

    formData.append(
      'description',
      form.description,
    )

    formData.append(
      'price',
      form.price,
    )

    formData.append(
      'audience',
      form.audience,
    )

    formData.append(
      'usp',
      form.usp,
    )

    formData.append(
      'brand_tone',
      form.brandTone,
    )

    const file =
      getImageFile()

    if (file) {
      formData.append(
        'image',
        file,
      )
    }

    return formData
  }

  // ---------------------------------------------------------
  // Generate campaign
  // ---------------------------------------------------------

  const handleGenerate = async () => {
    const requestId = ++generationId.current
    setError('')
    setGenerated(false)
    setApproved(false)
    setApprovalAcknowledged(false)
    setQuality(null)
    setLoading(true)

    if (!form.productName.trim()) {
      setError(
        'Please enter the product name.',
      )
      setLoading(false)
      return
    }

    if (!form.description.trim()) {
      setError(
        'Please enter the product description.',
      )
      setLoading(false)
      return
    }

    if (!form.price.trim()) {
      setError('Please enter the product price.')
      setLoading(false)
      return
    }

    if (!form.audience.trim()) {
      setError(
        'Please enter the target audience.',
      )
      setLoading(false)
      return
    }

    if (!form.usp.trim()) {
      setError(
        'Please enter the main selling point.',
      )
      setLoading(false)
      return
    }

    try {
      const response =
        await fetch(
          `${API}/api/generate-campaign`,
          {
            method: 'POST',
            body: createFormData(),
          },
        )

      const data =
        await response.json()

      if (requestId !== generationId.current) return

      if (
        !response.ok ||
        !data.ok
      ) {
        throw new Error(
          data.detail ||
            data.error ||
            'Campaign generation failed.',
        )
      }

      setCampaign(
        data.campaign ||
          emptyCampaign,
      )

      setPlatformImages(
        data.platform_images ||
          {},
      )
      setPlatformImageVariants(data.platform_image_variants || {})

      setImageErrors({ ...(data.platform_image_errors || {}), ...(data.platform_image_variant_errors || {}) })
      setQuality(data.quality || null)

      setScriptIdeas({})
      setGenerated(true)
      setApprovalAcknowledged(false)
    } catch (err) {
      if (requestId !== generationId.current) return
      setError(
        err.message ||
          'Something went wrong while generating the campaign.',
      )
    } finally {
      if (requestId === generationId.current) setLoading(false)
    }
  }

  const restartCampaign = () => {
    generationId.current += 1
    setForm({ ...emptyForm })
    setImageFile(null)
    setImagePreview(null)
    setCampaign({ platforms: {}, campaign_brain: {} })
    setPlatformImages({})
    setPlatformImageVariants({})
    setImageErrors({})
    setScriptIdeas({})
    setQuality(null)
    setApproved(false)
    setApprovalAcknowledged(false)
    setImageNeedsReselect(false)
    setStorageWarning(false)
    setActivePlatform('instagram')
    setActiveAssetKey('instagram')
    setLoading(false)
    setActionLoading('')
    setGenerated(false)
    setError('')
    setCopyStatus('')
    const imageInput = document.getElementById('product-image-input')
    if (imageInput) imageInput.value = ''
    for (const key of ['launchflow_image_pending', 'launchflow_preview']) {
      try { localStorage.removeItem(key) } catch {}
    }
  }

  // ---------------------------------------------------------
  // Caption regeneration
  // ---------------------------------------------------------

  const regenerateCaption = async () => {
    if (!activeContent) return
    const requestId = generationId.current

    setError('')
    setActionLoading('caption')

    try {
      const formData =
        new FormData()

      formData.append(
        'platform',
        activePlatform,
      )

      formData.append(
        'content_type',
        getContentType(
          activePlatform,
        ),
      )

      formData.append(
        'product_name',
        form.productName,
      )

      formData.append(
        'description',
        form.description,
      )

      formData.append(
        'price',
        form.price,
      )

      formData.append(
        'audience',
        form.audience,
      )

      formData.append(
        'usp',
        form.usp,
      )

      formData.append(
        'brand_tone',
        form.brandTone,
      )

      const response =
        await fetch(
          `${API}/api/regenerate-caption`,
          {
            method: 'POST',
            body: formData,
          },
        )

      const data =
        await response.json()

      if (requestId !== generationId.current) return

      if (
        !response.ok ||
        !data.ok
      ) {
        throw new Error(
          data.detail ||
            'Caption regeneration failed.',
        )
      }

      const updatedCampaign = applyPlatformCopy(campaign, activePlatform, data.content)
      updatePlatformCopy(activePlatform, data.content)
      setQuality(null)
      setApproved(false)
      setApprovalAcknowledged(false)
      const qualityResponse = await fetch(`${API}/api/quality-check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brief: toApiBrief(form), campaign: updatedCampaign }),
      })
      const qualityData = await qualityResponse.json()
      if (requestId !== generationId.current) return
      if (!qualityResponse.ok || !qualityData.ok) {
        throw new Error(qualityData.detail || 'Caption was regenerated, but quality checks could not be refreshed.')
      }
      setQuality(qualityData.quality)
    } catch (err) {
      if (requestId !== generationId.current) return
      setError(
        err.message ||
          'Could not regenerate caption.',
      )
    } finally {
      if (requestId === generationId.current) setActionLoading('')
    }
  }

  const downloadImage = async () => {
    if (!imageUrl) return
    try {
      const response = await fetch(imageUrl)
      if (!response.ok) throw new Error('Could not download this image.')
      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = href
      anchor.download = `${activeAsset?.label?.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'launchflow-asset'}.png`
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(href), 1000)
    } catch (err) {
      setError(err.message || 'Could not download image.')
    }
  }

  const copyText = async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(String(value || ''))
      setCopyStatus(successMessage)
      window.setTimeout(() => setCopyStatus(''), 1800)
    } catch {
      setError('Clipboard access is unavailable in this browser.')
    }
  }

  const scriptText = (script) => [
    script?.hook,
    script?.idea,
    ...(script?.scenes || []).map((scene) => [scene.visual, scene.spoken_or_text].filter(Boolean).join(' — ')),
    script?.cta,
  ].filter(Boolean).join('\n\n')

  // ---------------------------------------------------------
  // Script idea generation
  // ---------------------------------------------------------

  const generateScriptIdea =
    async () => {
      const requestId = generationId.current
      setError('')
      setActionLoading('script')

      try {
        const formData =
          new FormData()

      formData.append(
        'platform',
        activePlatform,
        )

        formData.append(
          'product_name',
          form.productName,
        )

        formData.append(
          'description',
          form.description,
        )

        formData.append(
          'audience',
          form.audience,
        )

        formData.append(
          'usp',
          form.usp,
        )

        formData.append(
          'brand_tone',
          form.brandTone,
        )

        const response =
          await fetch(
            `${API}/api/generate-video-script`,
            {
              method: 'POST',
              body: formData,
            },
          )

        const data =
          await response.json()

        if (requestId !== generationId.current) return

        if (
          !response.ok ||
          !data.ok
        ) {
          throw new Error(
            data.detail ||
              'Script idea generation failed.',
          )
        }

        setScriptIdeas(
          (previous) => ({
            ...previous,
            [activePlatform]:
              data.script,
          }),
        )
        setApproved(false)
        setApprovalAcknowledged(false)
      } catch (err) {
        if (requestId !== generationId.current) return
        setError(
          err.message ||
            'Could not generate script idea.',
        )
      } finally {
        if (requestId === generationId.current) setActionLoading('')
      }
    }

  // ---------------------------------------------------------
  // Update copy
  // ---------------------------------------------------------

  const updatePlatformCopy = (
    platform,
    generatedCopy,
  ) => {
    setCampaign(
      (previous) => {
        const copy =
          structuredClone(
            previous,
          )

        if (!copy.platforms) {
          copy.platforms = {}
        }

        if (
          !copy.platforms[
            platform
          ]
        ) {
          copy.platforms[
            platform
          ] = {}
        }

        const current =
          copy.platforms[
            platform
          ]

        if (
          platform ===
          'instagram'
        ) {
          current.post = {
            ...(current.post ||
              {}),
            caption:
              generatedCopy.text,
            cta:
              generatedCopy.cta ||
              current.post?.cta ||
              '',
            hashtags:
              generatedCopy.hashtags ||
              current.post
                ?.hashtags ||
              [],
          }
        }

        if (
          platform ===
          'youtube'
        ) {
          current.short = {
            ...(current.short ||
              {}),
            caption:
              generatedCopy.text,
            cta:
              generatedCopy.cta ||
              current.short?.cta ||
              '',
          }
        }

        if (
          platform ===
          'facebook'
        ) {
          current.post = {
            ...(current.post ||
              {}),
            caption:
              generatedCopy.text,
            cta:
              generatedCopy.cta ||
              current.post?.cta ||
              '',
          }
        }

        if (
          platform ===
          'x'
        ) {
          current.post = {
            ...(current.post ||
              {}),
            text:
              generatedCopy.text,
            cta:
              generatedCopy.cta ||
              current.post?.cta ||
              '',
          }
        }

        if (
          platform ===
          'whatsapp'
        ) {
          current.message = {
            ...(current.message ||
              {}),
            text:
              generatedCopy.text,
            cta:
              generatedCopy.cta ||
              current.message?.cta ||
              '',
          }
        }

        return copy
      },
    )
  }

  const downloadApprovedCampaign = () => {
    if (!approved || !quality?.completed) return
    const exportData = {
      app: 'LaunchFlow AI',
      exported_at: new Date().toISOString(),
      approved: true,
      brief: toApiBrief(form),
      campaign,
      quality,
      platform_images: Object.fromEntries(Object.entries(platformImages).map(([key, value]) => [key, `${API}${value}`])),
    }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = `launchflow-campaign-${Date.now()}.json`
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(href), 1000)
  }

  const qualityNeedsAcknowledgement = Boolean(quality?.checks?.some((check) => !check.passed))

  // ---------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------

  const getContentType =
    (platform) => {
      if (
        platform ===
        'instagram'
      ) {
        return 'Instagram feed caption'
      }

      if (
        platform ===
        'youtube'
      ) {
        return 'YouTube Short caption'
      }

      if (
        platform ===
        'facebook'
      ) {
        return 'Facebook promotional post'
      }

      if (
        platform ===
        'x'
      ) {
        return 'X promotional post'
      }

      return 'WhatsApp promotional message'
    }

  const activeContent =
    campaign?.platforms?.[
      activePlatform
    ] || null

  const activeCaption = activePlatform === 'instagram'
    ? activeContent?.post?.caption
    : activePlatform === 'youtube'
      ? activeContent?.short?.caption
      : activePlatform === 'facebook'
        ? activeContent?.post?.caption
        : activePlatform === 'x'
          ? activeContent?.post?.text
          : activeContent?.message?.text

  const activePlatformName =
    platforms.find(
      (platform) =>
        platform.id ===
        activePlatform,
    )?.name ||
    activePlatform

  const activeAsset = (campaignAssets[activePlatform] || []).find((asset) => asset.key === activeAssetKey) || campaignAssets[activePlatform]?.[0]
  const activeImage = activeAsset?.key === activePlatform ? platformImages[activePlatform] : platformImageVariants[activeAsset?.key]
  const imageUrl = activeImage ? `${API}${activeImage}` : null

  const reviewNeeded = qualityNeedsAcknowledgement

  const renderCaption = (text, label = 'Caption') => (
    <div className="caption-copy-row">
      <p><b>{label}:</b> {text}</p>
      <button
        type="button"
        className="copy-icon-button"
        aria-label={`Copy ${label.toLowerCase()}`}
        title={`Copy ${label.toLowerCase()}`}
        onClick={() => copyText(text, `${label} copied.`)}
        disabled={!text}
      >
        <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="8" y="8" width="12" height="12" rx="2" />
          <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
        </svg>
      </button>
    </div>
  )

  // ---------------------------------------------------------
  // Platform renderers
  // ---------------------------------------------------------

  const renderInstagram =
    () => {
      const content =
        activeContent || {}

      return (
        <>
          {content.post && (
            <div className="content-block">
              <strong>
                Instagram Post
              </strong>

              {renderCaption(content.post.caption, 'Instagram caption')}

              {content.post
                .hashtags
                ?.length > 0 && (
                <p className="hashtags">
                  {content.post.hashtags.join(
                    ' ',
                  )}
                </p>
              )}

              <strong>
                CTA:{' '}
                {
                  content.post.cta
                }
              </strong>
            </div>
          )}

          {content.reel && (
            <div className="content-block">
              <strong>
                Instagram Reel
              </strong>

              {renderCaption(content.reel.caption, 'Reel caption')}

              <strong>
                CTA:{' '}
                {
                  content.reel.cta
                }
              </strong>
            </div>
          )}

          {content.story && (
            <div className="content-block">
              <strong>
                Instagram Story
              </strong>

              <p>
                <b>
                  Frame 1:
                </b>{' '}
                {
                  content.story
                    .frame_1
                }
              </p>

              <p>
                <b>
                  Frame 2:
                </b>{' '}
                {
                  content.story
                    .frame_2
                }
              </p>

              <p>
                <b>
                  Frame 3:
                </b>{' '}
                {
                  content.story
                    .frame_3
                }
              </p>

              <strong>
                CTA:{' '}
                {
                  content.story.cta
                }
              </strong>
            </div>
          )}
        </>
      )
    }

  const renderYoutube =
    () => {
      const content =
        activeContent || {}

      return (
        <>
          {content.short && (
            <div className="content-block">
              <strong>
                YouTube Short
              </strong>

              {renderCaption(content.short.caption, 'YouTube Short caption')}

              <strong>
                CTA:{' '}
                {
                  content.short.cta
                }
              </strong>
            </div>
          )}

          {content.thumbnail && (
            <div className="content-block">
              <strong>
                YouTube Thumbnail
              </strong>

              <p>
                <b>
                  Text:
                </b>{' '}
                {
                  content
                    .thumbnail
                    .text
                }
              </p>

              <p>
                <b>
                  Visual:
                </b>{' '}
                {
                  content
                    .thumbnail
                    .visual_concept
                }
              </p>
            </div>
          )}
        </>
      )
    }

  const renderFacebook =
    () => {
      const content =
        activeContent || {}

      return (
        <div className="content-block">
          <strong>
            Facebook Post
          </strong>

          {renderCaption(content.post?.caption, 'Facebook caption')}

          <strong>
            CTA:{' '}
            {
              content.post?.cta
            }
          </strong>
        </div>
      )
    }

  const renderX = () => {
    const content =
      activeContent || {}

    return (
      <div className="content-block">
        <strong>
          X Post
        </strong>

        {renderCaption(content.post?.text, 'X post')}

        <small>
          {
            (
              content.post
                ?.text || ''
            ).length
          }
          /280 characters
        </small>

        <p>
          <strong>
            CTA:{' '}
            {
              content.post?.cta
            }
          </strong>
        </p>
      </div>
    )
  }

  const renderWhatsapp =
    () => {
      const content =
        activeContent || {}

      return (
        <>
          {content.message && (
            <div className="content-block">
              <strong>
                WhatsApp Message
              </strong>

              {renderCaption(content.message.text, 'WhatsApp message')}

              <strong>
                CTA:{' '}
                {
                  content.message
                    .cta
                }
              </strong>
            </div>
          )}

          {content.status && (
            <div className="content-block">
              <strong>
                WhatsApp Status
              </strong>

              <p>
                <b>
                  Frame 1:
                </b>{' '}
                {
                  content.status
                    .frame_1
                }
              </p>

              <p>
                <b>
                  Frame 2:
                </b>{' '}
                {
                  content.status
                    .frame_2
                }
              </p>

              <p>
                <b>
                  Frame 3:
                </b>{' '}
                {
                  content.status
                    .frame_3
                }
              </p>

              <strong>
                CTA:{' '}
                {
                  content.status.cta
                }
              </strong>
            </div>
          )}
        </>
      )
    }

  const renderPlatformContent =
    () => {
      if (!activeContent) {
        return (
          <p>
            Your platform-specific
            campaign content will
            appear here after
            generation.
          </p>
        )
      }

      if (
        activePlatform ===
        'instagram'
      ) {
        return renderInstagram()
      }

      if (
        activePlatform ===
        'youtube'
      ) {
        return renderYoutube()
      }

      if (
        activePlatform ===
        'facebook'
      ) {
        return renderFacebook()
      }

      if (
        activePlatform === 'x'
      ) {
        return renderX()
      }

      return renderWhatsapp()
    }

  // ---------------------------------------------------------
  // UI
  // ---------------------------------------------------------

  return (
    <div className="app">
      <header className="navbar">
        <div className="brand">
          <div className="brand-mark">
            L
          </div>

          <div>
            <h1>
              LaunchFlow AI
            </h1>

            <span>
              AI Content Studio
            </span>
          </div>
        </div>

      </header>

      <main className="dashboard">
        <section className="hero-section">
          <div>
            <p className="eyebrow">
              ONE PRODUCT. ONE CAMPAIGN BRAIN.
            </p>

            <h2>
              Turn your product idea
              into a
              <span>
                {' '}
                campaign ready to
                launch.
              </span>
            </h2>

            <p className="hero-description">
              Give LaunchFlow AI your
              product details and image.
              The Campaign Brain creates
              coordinated, platform-ready
              content for your brand.
            </p>
          </div>
        </section>

        <section className="workspace">
          <div className="brief-panel">
            <div className="section-heading">
              <div>
                <span className="step-number">
                  01
                </span>

                <h3>
                  Product Brief
                </h3>
              </div>

              <div className="brief-heading-actions">
                <span className="required">Required</span>
                <button className="restart-button" type="button" onClick={restartCampaign}>Restart</button>
              </div>
            </div>

            <label>
              Product name

              <input
                name="productName"
                value={
                  form.productName
                }
                onChange={
                  handleChange
                }
                placeholder="e.g. Berry Bliss Cheesecake"
              />
            </label>

            <label>
              Description

              <textarea
                name="description"
                value={
                  form.description
                }
                onChange={
                  handleChange
                }
                rows="4"
                placeholder="Tell us about your product..."
              />
            </label>

            <div className="two-column">
              <label>
                Price

                <input
                  name="price"
                  value={
                    form.price
                  }
                  onChange={
                    handleChange
                  }
                  placeholder="₹499"
                />
              </label>

              <label>
                Target audience

                <input
                  name="audience"
                  value={
                    form.audience
                  }
                  onChange={
                    handleChange
                  }
                  placeholder="College students"
                />
              </label>
            </div>

            <label>
              Main selling point

              <textarea
                name="usp"
                value={form.usp}
                onChange={
                  handleChange
                }
                rows="3"
                placeholder="What makes your product special?"
              />
            </label>

            <div className="two-column">
              <label>
                Brand tone

                <select
                  name="brandTone"
                  value={
                    form.brandTone
                  }
                  onChange={
                    handleChange
                  }
                >
                  <option value="friendly">
                    Friendly
                  </option>

                  <option value="professional">
                    Professional
                  </option>

                  <option value="playful">
                    Playful
                  </option>

                  <option value="premium">
                    Premium
                  </option>
                </select>
              </label>
            </div>

            <label className="upload-box">
              <span className="upload-icon">
                ＋
              </span>

              <strong>
                {imagePreview
                  ? 'Product image selected'
                  : 'Upload product image'}
              </strong>

              <small>
                PNG, JPG or WEBP
              </small>

              <input
                id="product-image-input"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={
                  handleImageChange
                }
              />
            </label>

            {imagePreview && (
              <img
                className="uploaded-preview"
                src={imagePreview}
                alt="Product preview"
              />
            )}

            {imageNeedsReselect && !imagePreview && (
              <p className="status-warning">
                Your uploaded image is kept only in memory for privacy and storage reliability. Select it again after a refresh to regenerate images.
              </p>
            )}

            {storageWarning && (
              <p className="status-warning">
                Browser storage is unavailable or full. This session will continue, but some data may not survive a refresh.
              </p>
            )}

            {error && (
              <p className="error-message">
                {error}
              </p>
            )}

            <button
              className="generate-button"
              type="button"
              onClick={
                handleGenerate
              }
              disabled={loading}
            >
              {loading
                ? 'Generating Campaign...'
                : 'Generate Campaign →'}
            </button>
          </div>

          <div className="campaign-panel">
            <div className="section-heading">
              <div>
                <span className="step-number">
                  02
                </span>

                <h3>
                  Campaign Studio
                </h3>
              </div>

              <span className="draft-badge">
                {generated
                  ? 'GENERATED'
                  : 'DRAFT'}
              </span>
            </div>

            <div className="platform-tabs">
              {platforms.map(
                (platform) => (
                  <button
                    key={
                      platform.id
                    }
                    className={
                      activePlatform ===
                      platform.id
                        ? 'platform active'
                        : 'platform'
                    }
                    onClick={() =>
                      {
                        setActivePlatform(platform.id)
                        setActiveAssetKey(campaignAssets[platform.id]?.[0]?.key || platform.id)
                      }
                    }
                    type="button"
                  >
                    <span>
                      {
                        platform.icon
                      }
                    </span>

                    {
                      platform.name
                    }
                  </button>
                ),
              )}
            </div>

            <div className="campaign-preview">
              <div className="asset-variant-tabs" aria-label="Image format">
                {(campaignAssets[activePlatform] || []).map((asset) => (
                  <button key={asset.key} type="button" className={activeAssetKey === asset.key ? 'active' : ''} onClick={() => setActiveAssetKey(asset.key)}>
                    {asset.label}
                  </button>
                ))}
              </div>
              <div className="preview-header">
                <div>
                  <span className="preview-label">
                    GENERATED IMAGE
                  </span>

                  <h4>
                    {activeAsset?.label || activePlatformName}
                  </h4>
                  <small>{activeAsset?.dimensions}</small>
                </div>

                <span className="ai-badge">
                  PRODUCT COMPOSITION
                </span>
              </div>

              {imageUrl ? (
                <img
                  className="campaign-image"
                  src={imageUrl}
                  alt={`${activeAsset?.label || activePlatformName} campaign image`}
                />
              ) : (
                <div className="empty-preview">
                  <span>
                    ✦
                  </span>

                  <p>
                    Your generated
                    campaign visual
                    will appear here
                    after generation.
                  </p>
                </div>
              )}

              {imageErrors[activeAssetKey] && (
                <p className="error-message">
                  {activeAsset?.label || activePlatformName} image: {imageErrors[activeAssetKey]}
                </p>
              )}

              <div className="asset-actions">
                <button type="button" onClick={downloadImage} disabled={!imageUrl}>↓ Download Image</button>
                <button
                  type="button"
                  onClick={() => copyText(activeCaption, 'Caption copied.')}
                  disabled={!activeCaption}
                >
                  Copy Caption
                </button>
                <button
                  type="button"
                  onClick={
                    regenerateCaption
                  }
                  disabled={
                    actionLoading ===
                      'caption' ||
                    !generated
                  }
                >
                  {actionLoading === 'caption' ? 'Regenerating Caption...' : '↻ Regenerate Caption'}
                </button>

                {(activePlatform === 'instagram' || activePlatform === 'youtube') && (
                  <button type="button" onClick={generateScriptIdea} disabled={actionLoading === 'script' || !generated}>
                    {actionLoading === 'script' ? 'Generating Script...' : activePlatform === 'instagram' ? '✦ Generate Reel Script' : '✦ Generate Short Script'}
                  </button>
                )}
              </div>
              {copyStatus && <p className="copy-status" role="status">{copyStatus}</p>}

              {(activePlatform === 'instagram' || activePlatform === 'youtube') && scriptIdeas[activePlatform] && (
                <div className="content-block">
                  <strong>
                    {activePlatform === 'instagram' ? 'Instagram Reel Script' : 'YouTube Short Script'}
                  </strong>

                  <p>
                    <b>
                      Title:
                    </b>{' '}
                    {
                      scriptIdeas[
                        activePlatform
                      ].title
                    }
                  </p>

                  <p>
                    <b>
                      Hook:
                    </b>{' '}
                    {
                      scriptIdeas[
                        activePlatform
                      ].hook
                    }
                  </p>

                  <p>
                    <b>
                      Idea:
                    </b>{' '}
                    {
                      scriptIdeas[
                        activePlatform
                      ].idea
                    }
                  </p>

                  {scriptIdeas[
                    activePlatform
                  ].scenes?.map(
                    (scene) => (
                      <p
                        key={
                          scene.scene
                        }
                      >
                        <b>
                          Scene{' '}
                          {
                            scene.scene
                          }:
                        </b>{' '}
                        {
                          scene.visual
                        }
                        {scene.spoken_or_text
                          ? ` — ${scene.spoken_or_text}`
                          : ''}
                      </p>
                    ),
                  )}

                  <strong>
                    CTA:{' '}
                    {
                      scriptIdeas[
                        activePlatform
                      ].cta
                    }
                  </strong>
                  <div className="asset-actions">
                    <button type="button" onClick={() => copyText(scriptText(scriptIdeas[activePlatform]), 'Script copied.')}>Copy Script</button>
                    <button type="button" onClick={generateScriptIdea} disabled={actionLoading === 'script'}>Regenerate Script</button>
                  </div>
                </div>
              )}

              <div className="generated-copy">
                <span>
                  PLATFORM CONTENT
                </span>

                {renderPlatformContent()}
              </div>
            </div>
          </div>
        </section>

        <section className="approval-panel" aria-labelledby="quality-title">
          <div className="approval-heading">
            <div>
              <span className="step-number">04</span>
              <h3 id="quality-title">Quality checks &amp; approval</h3>
            </div>
            <span className={approved ? 'approval-badge approved' : 'approval-badge'}>
              {approved ? 'APPROVED' : generated ? 'AWAITING REVIEW' : 'NOT GENERATED'}
            </span>
          </div>

          {quality?.completed ? (
            <>
              <p className={quality.checks.every((check) => check.passed) ? 'quality-summary pass' : 'quality-summary warning'}>
                {quality.summary}
              </p>
              <ul className="quality-list">
                {quality.checks.map((check, index) => (
                  <li key={`${check.platform || 'campaign'}-${check.check}-${check.field || index}`} className={check.passed ? 'check-pass' : check.severity === 'warning' ? 'check-warning' : 'check-fail'}>
                    <span>{check.passed ? '✓' : check.severity === 'warning' ? '!' : '×'}</span>
                    <div>
                      <strong>{check.platform ? `${check.platform}: ` : ''}{check.check.replaceAll('_', ' ')}</strong>
                      <small>{check.detail}</small>
                    </div>
                  </li>
                ))}
              </ul>

              {reviewNeeded && !approved && (
                <label className="approval-acknowledgement">
                  <input type="checkbox" checked={approvalAcknowledged} onChange={(event) => setApprovalAcknowledged(event.target.checked)} />
                  I reviewed the flagged checks and want to approve this campaign anyway.
                </label>
              )}

              {approved ? (
                <div className="approval-actions">
                  <p className="approval-confirmation">Campaign approved. The approved brief, content, quality report, and asset links are ready to export.</p>
                  <button type="button" className="approve-button" onClick={downloadApprovedCampaign}>Download approved campaign</button>
                  <button type="button" className="review-button" onClick={() => setApproved(false)}>Return to review</button>
                </div>
              ) : (
                <button
                  type="button"
                  className="approve-button"
                  disabled={!generated || !quality.completed || (reviewNeeded && !approvalAcknowledged)}
                  onClick={() => setApproved(true)}
                >
                  Approve campaign
                </button>
              )}
            </>
          ) : (
            <p className="quality-summary">Generate a campaign to run the required quality checks before approval.</p>
          )}
        </section>

        <section className="workflow">
          <div className="workflow-heading">
            <span className="step-number">
              05
            </span>

            <div>
              <h3>
                Campaign Workflow
              </h3>

              <p>
                AI generation with
                human approval.
              </p>
            </div>
          </div>

          <div className="workflow-steps">
            <div className="workflow-step active">
              <span>
                1
              </span>

              <strong>
                Understand
              </strong>

              <small>
                Product + audience
              </small>
            </div>

            <div className="workflow-line" />

            <div className="workflow-step">
              <span>
                2
              </span>

              <strong>
                Create
              </strong>

              <small>
                Platform content
              </small>
            </div>

            <div className="workflow-line" />

            <div className="workflow-step">
              <span>
                3
              </span>

              <strong>
                Check
              </strong>

              <small>
                Quality &
                consistency
              </small>
            </div>

            <div className="workflow-line" />

            <div className="workflow-step">
              <span>
                4
              </span>

              <strong>
                Approve
              </strong>

              <small>
                Human review
              </small>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
