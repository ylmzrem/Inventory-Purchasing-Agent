# Veri Sözlüğü (ERP Veritabanı Şeması)

## 1. `products` (Ürünler ve Sipariş Kuralları)
| Sütun | Tip | Açıklama |
|---|---|---|
| `product_id` | TEXT (PK) | Benzersiz ürün kodu (Örn: `PRD-001`) |
| `name` | TEXT | Malzeme/ürün adı |
| `unit` | TEXT | Ölçü birimi (`adet`, `metre`, `kg`) |
| `safety_stock` | REAL | Hedeflenen emniyet stoku miktarı |
| `reorder_point` | REAL | Yeniden sipariş tetikleme seviyesi |
| `min_order_qty` | REAL | Ürün bazlı minimum sipariş miktarı (MOQ) |
| `pack_multiple` | REAL | Sipariş miktarının yuvarlanacağı paket/lot katı |

## 2. `inventory` (Anlık Stok Durumu)
| Sütun | Tip | Açıklama |
|---|---|---|
| `product_id` | TEXT (FK) | İlgili ürün kodu |
| `physical_stock` | REAL | Depodaki toplam fiziksel miktar |
| `allocated_stock` | REAL | Mevcut üretim/siparişlere ayrılmış (bloke) miktar |
| `updated_at` | TEXT | Stok sayım/güncelleme zaman damgası (ISO-8601) |

## 3. `demand_forecast` (Tarihli Talep Tahmini)
| Sütun | Tip | Açıklama |
|---|---|---|
| `demand_id` | INTEGER (PK) | Talep kayıt kimliği |
| `product_id` | TEXT (FK) | İlgili ürün kodu |
| `demand_date` | TEXT | İhtiyaç tarihi (`YYYY-MM-DD`) |
| `quantity` | REAL | Talep edilen miktar |
| `is_covered_by_allocation` | INTEGER | `1` ise bloke stokla karşılanmıştır (çift sayım önlenir) |

## 4. `open_orders` (Açık Satın Alma Siparişleri)
| Sütun | Tip | Açıklama |
|---|---|---|
| `po_id` | TEXT (PK) | Satın alma sipariş numarası (`PO-...`) |
| `product_id` | TEXT (FK) | İlgili ürün kodu |
| `quantity` | REAL | Gelecek sipariş miktarı |
| `expected_date` | TEXT | Depoya beklenen giriş tarihi (`YYYY-MM-DD`) |
| `status` | TEXT | Sipariş durumu (`CONFIRMED`, `IN_TRANSIT`, `DELAYED`) |

## 5. `suppliers`, `supplier_products`, `price_tiers` (Tedarikçi ve Kademeli Fiyatlar)
| Sütun | Tip | Açıklama |
|---|---|---|
| `supplier_id` | TEXT (PK) | Tedarikçi kimliği (`SUP-...`) |
| `reliability_score` | REAL | 0–100 arası tedarikçi güvenilirlik puanı |
| `notes` | TEXT | Tedarikçi serbest metin notları (prompt injection testleri dahil) |
| `lead_time_days` | INTEGER | Tedarik süresi (gün) |
| `freight_cost` | REAL | Sabit nakliye bedeli |
| `currency` | TEXT | Fiyat ve nakliye para birimi (`TRY`, `USD`, `EUR`) |
| `unit_price` | REAL | `min_qty` - `max_qty` aralığı için birim fiyat |

## 6. `purchase_requisitions` (Test Ortamı Satın Alma Talepleri)
| Sütun | Tip | Açıklama |
|---|---|---|
| `req_id` | TEXT (PK) | Talep kimliği (`REQ-...`) |
| `status` | TEXT | `DRAFT` (taslak), `APPROVED` (onaylı), `SAVED` (kaydedildi), `REJECTED` (reddedildi) |
| `data_snapshot_hash` | TEXT | Taslak anındaki stok/sipariş/fiyat verilerinin SHA-256 özeti |
| `rationale` | TEXT | Miktar ve tedarikçi seçim gerekçesi |