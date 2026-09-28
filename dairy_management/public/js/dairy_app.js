(() => {
    const root = document.getElementById("dairy-root");

    if (!root) {
        console.error("Dairy App root not found");
        return;
    }

    const S = {
        view: "home",
        products: [],
        offers: [],
        upcoming: [],
        delivered: [],
        posts: [],
        wallet: 0,
        category: "All",
        productTab: "Dairy",
        homeTab: "offers",
        orderTab: "upcoming",
        search: ""
    };

    const categories = [
        "All",
        "Milk",
        "Curd",
        "Paneer",
        "Ghee",
        "Beverages",
        "Snacks",
        "Organic",
        "Others"
    ];

    const esc = (value) =>
        String(value ?? "").replace(/[&<>"']/g, (m) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        }[m]));

    const money = (value) => {
        if (window.DairyApp && DairyApp.money) {
            return DairyApp.money(value);
        }

        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 2
        }).format(Number(value || 0));
    };

    const api = async (method, args = {}) => {
        return DairyApp.call(method, args);
    };

    const empty = (text) => `
        <div class="card dairy-empty">
            ${esc(text)}
        </div>
    `;

    const toast = (text) => {
        const el = document.createElement("div");
        el.className = "toast";
        el.textContent = text;
        document.body.appendChild(el);

        setTimeout(() => {
            el.remove();
        }, 1800);
    };

    /* ---------------------------------------------------------
       NAVIGATION
    --------------------------------------------------------- */

    const nav = (active) => `
        <div class="bottom-nav">
            <button class="nav-item ${active === "home" ? "active" : ""}"
                    data-view="home">
                <span class="nav-icon">⌂</span>
                <span>Home</span>
            </button>

            <button class="nav-item ${active === "products" ? "active" : ""}"
                    data-view="products">
                <span class="nav-icon">▦</span>
                <span>Products</span>
            </button>

            <button class="nav-item ${active === "orders" ? "active" : ""}"
                    data-view="orders">
                <span class="nav-icon">▤</span>
                <span>Orders</span>
            </button>

            <button class="nav-item ${active === "offers" ? "active" : ""}"
                    data-view="offers">
                <span class="nav-icon">🏷</span>
                <span>Offers</span>
            </button>

            <button class="nav-item ${active === "account" ? "active" : ""}"
                    data-view="account">
                <span class="nav-icon">♙</span>
                <span>Account</span>
            </button>
        </div>
    `;

    const bindNavigation = () => {
        document.querySelectorAll("[data-view]").forEach((element) => {
            element.onclick = () => {
                S.view = element.dataset.view;
                render();
            };
        });
    };

    /* ---------------------------------------------------------
       HEADER
    --------------------------------------------------------- */

    const header = (title, subtitle = "Fresh dairy delivered to your door") => `
        <div class="dairy-header" style="color:#111827;">
            <div class="dairy-header-main">
                <div class="dairy-title" style="color:#111827;">
                    ${title}
                </div>

                <div class="dairy-sub" style="color:#111827;">
                    ${subtitle}
                </div>
            </div>

            <button
                class="wallet-pill"
                style="color:#111827;"
                onclick="openAddMoney()">
                ${money(S.wallet)}
            </button>
        </div>
    `;

    /* ---------------------------------------------------------
       PRODUCT CARD
    --------------------------------------------------------- */

    const productCard = (product, options = {}) => {
        const name = product.item_name || product.name || "Dairy Product";
        const image = product.image || "/assets/frappe/images/ui/avatar.png";
        const price = Number(product.standard_rate || product.price || 0);

        const oldPrice =
            Number(
                product.old_price ||
                product.mrp ||
                product.list_price ||
                0
            );

        const size =
            product.stock_uom ||
            product.uom ||
            product.description ||
            "Unit";

        return `
            <div class="card product-card"
                 style="
                    color:#111827;
                    background:#ffffff;
                    border:1px solid #e5e7eb;
                 ">

                <div class="product-image-wrap">
                    <img
                        src="${esc(image)}"
                        alt="${esc(name)}"
                        class="product-image"
                    >
                </div>

                <div class="product-info">

                    <div class="product-name"
                         style="color:#111827;">
                        ${esc(name)}
                    </div>

                    <div class="dairy-sub"
                         style="color:#111827;">
                        ${esc(size)}
                    </div>

                    ${
                        product.short_description
                            ? `
                                <div class="product-description"
                                     style="color:#111827;">
                                    ${esc(product.short_description)}
                                </div>
                              `
                            : ""
                    }

                    <div class="product-price-row">

                        <span class="price"
                              style="color:#111827;">
                            ${money(price)}
                        </span>

                        ${
                            oldPrice > price
                                ? `
                                    <span
                                        class="old-price"
                                        style="
                                            color:#6b7280;
                                            text-decoration:line-through;
                                        ">
                                        ${money(oldPrice)}
                                    </span>
                                  `
                                : ""
                        }

                    </div>

                    <div class="product-actions">

                        ${
                            options.subscribe
                                ? `
                                    <button
                                        class="btn btn-light"
                                        style="color:#111827;"
                                        onclick="subscribeProduct('${esc(product.name)}')">
                                        Subscribe
                                    </button>
                                  `
                                : ""
                        }

                        <button
                            class="btn btn-primary"
                            onclick="addProduct('${esc(product.name)}')">
                            Add
                        </button>

                    </div>

                </div>
            </div>
        `;
    };

    /* ---------------------------------------------------------
       HOME - OFFER CARD
    --------------------------------------------------------- */

    const offerCard = (offer) => `
        <div class="card home-offer-card"
             style="
                background:#ffffff;
                color:#111827;
                border:1px solid #e5e7eb;
             ">

            <div>
                ${
                    offer.title
                        ? `
                            <div class="offer-title"
                                 style="color:#111827;">
                                ${esc(offer.title)}
                            </div>
                          `
                        : ""
                }

                <div class="offer-description"
                     style="color:#111827;">
                    ${esc(
                        offer.description ||
                        "Special price for you"
                    )}
                </div>
            </div>

            ${
                offer.discount_percentage
                    ? `
                        <span
                            class="offer-badge"
                            style="color:#111827;">
                            ${esc(offer.discount_percentage)}% OFF
                        </span>
                      `
                    : ""
            }

            ${
                offer.discount_amount
                    ? `
                        <span
                            class="offer-badge"
                            style="color:#111827;">
                            ${money(offer.discount_amount)} OFF
                        </span>
                      `
                    : ""
            }

        </div>
    `;

    /* ---------------------------------------------------------
       UPCOMING ORDER
    --------------------------------------------------------- */

    const orderCard = (order) => {
        const deliveryDate = order.delivery_date
            ? new Date(order.delivery_date)
            : null;

        const day = deliveryDate
            ? deliveryDate.getDate()
            : "—";

        const month = deliveryDate
            ? deliveryDate.toLocaleString("en", {
                month: "short"
            })
            : "";

        const paused = order.status === "Paused";

        return `
            <div class="card order-row"
                 style="
                    color:#111827;
                    background:#ffffff;
                    border:1px solid #e5e7eb;
                 ">

                <div class="date-box">
                    <b style="color:#111827;">
                        ${day}
                    </b>

                    <div style="color:#111827;">
                        ${month}
                    </div>
                </div>

                <div style="flex:1;">

                    <div style="
                        display:flex;
                        justify-content:space-between;
                        gap:8px;
                    ">

                        <b style="color:#111827;">
                            ${esc(
                                order.item_summary ||
                                order.name ||
                                "Order"
                            )}
                        </b>

                        <span
                            class="status ${paused ? "pause" : "ok"}"
                            style="color:#111827;">
                            ${esc(order.status || "Upcoming")}
                        </span>

                    </div>

                    <div class="dairy-sub"
                         style="color:#111827;">
                        Delivery by
                        ${esc(order.delivery_time || "7:00 AM")}
                    </div>

                    <div
                        style="
                            margin-top:7px;
                            font-weight:800;
                            color:#111827;
                        ">
                        ${money(order.order_total)}
                    </div>

                    <div
                        style="
                            display:flex;
                            gap:8px;
                            margin-top:10px;
                            flex-wrap:wrap;
                        ">

                        <button
                            class="btn btn-light"
                            style="color:#111827;"
                            onclick="toggleOrder(
                                '${esc(order.name)}',
                                '${paused ? "resume" : "pause"}'
                            )">
                            ${paused ? "Resume" : "Pause"}
                        </button>

                        <button
                            class="btn btn-primary"
                            onclick="addItemsToOrder('${esc(order.name)}')">
                            + Add Items
                        </button>

                    </div>

                </div>
            </div>
        `;
    };

    /* ---------------------------------------------------------
       HOME
    --------------------------------------------------------- */

    function home() {

        const newArrivals = S.products.slice(0, 6);

        const offersHtml =
            S.offers
                .slice(0, 3)
                .map(offerCard)
                .join("") ||
            empty("No active offers");

        const arrivalsHtml =
            newArrivals
                .map((product) =>
                    productCard(product, {
                        subscribe: true
                    })
                )
                .join("") ||
            empty("No new arrivals");

        return `
            <div
                class="dairy-home"
                style="
                    background:#ffffff;
                    color:#111111;
                "
            >

                <!-- HEADER -->

                <div
                    class="dairy-header"
                    style="
                        background:#ffffff;
                        color:#111111;
                    "
                >

                    <div class="dairy-header-main">

                        <div
                            class="dairy-title"
                            style="color:#111111;"
                        >
                            Hi, Sarath 👋
                        </div>

                        <div
                            class="dairy-sub"
                            style="color:#111111;"
                        >
                            Fresh dairy delivered to your door
                        </div>

                    </div>

                    <button
                        class="wallet-pill"
                        style="
                            color:#111111;
                            cursor:pointer;
                        "
                        onclick="openAddMoney()"
                    >
                        ${money(S.wallet)}
                    </button>

                </div>


                <!-- WALLET -->

                <div class="dairy-section">

                    <div
                        class="card wallet-home-card"
                        style="
                            background:#ffffff;
                            color:#111111;
                            border:1px solid #e5e7eb;
                        "
                    >

                        <div>

                            <div
                                style="
                                    font-size:13px;
                                    color:#111111;
                                "
                            >
                                Wallet Balance
                            </div>

                            <div
                                style="
                                    font-size:24px;
                                    font-weight:800;
                                    color:#111111;
                                    margin-top:3px;
                                "
                            >
                                ${money(S.wallet)}
                            </div>

                        </div>

                        <button
                            class="btn btn-primary"
                            onclick="openAddMoney()"
                        >
                            + Add Money
                        </button>

                    </div>

                </div>


                <!-- HERO -->

                <div class="dairy-section">

                    <div
                        class="hero"
                        style="
                            color:#111111;
                        "
                    >

                        <b
                            style="
                                font-size:27px;
                                color:#111111;
                            "
                        >
                            Pure Milk.<br>
                            Healthy Life.
                        </b>

                        <p style="color:#111111;">
                            Farm fresh dairy delivered to your home.
                        </p>

                        <button
                            class="btn btn-light"
                            style="color:#111111;"
                            data-view="products"
                        >
                            Shop Now
                        </button>

                    </div>

                </div>


                <!-- OFFERS / NEW ARRIVALS -->

                <div class="dairy-section">

                    <div
                        style="
                            display:flex;
                            justify-content:space-between;
                            align-items:center;
                            margin-bottom:12px;
                        "
                    >

                        <div
                            class="home-tabs"
                            style="
                                display:flex;
                                gap:8px;
                            "
                        >

                            <button
                                class="chip ${S.homeTab === "offers" ? "active" : ""}"
                                style="color:#111111;"
                                onclick="setHomeTab('offers')"
                            >
                                Today's Offers
                            </button>

                            <button
                                class="chip ${S.homeTab === "new" ? "active" : ""}"
                                style="color:#111111;"
                                onclick="setHomeTab('new')"
                            >
                                New Arrivals
                            </button>

                        </div>

                        <button
                            class="btn btn-light"
                            style="color:#111111;"
                            data-view="${
                                S.homeTab === "offers"
                                    ? "offers"
                                    : "products"
                            }"
                        >
                            View All
                        </button>

                    </div>


                    ${
                        S.homeTab === "offers"
                            ? `
                                <div class="home-offers-list">
                                    ${offersHtml}
                                </div>
                              `
                            : `
                                <div class="home-product-list">
                                    ${arrivalsHtml}
                                </div>
                              `
                    }

                </div>


                <!-- UPCOMING ORDERS -->

                <div class="dairy-section">

                    <div
                        style="
                            display:flex;
                            justify-content:space-between;
                            align-items:center;
                        "
                    >

                        <h3
                            style="
                                color:#111111;
                                margin:0;
                            "
                        >
                            Upcoming Orders
                        </h3>

                        <button
                            class="btn btn-light"
                            style="color:#111111;"
                            data-view="orders"
                        >
                            View All
                        </button>

                    </div>

                    <div style="margin-top:12px;">

                        ${
                            S.upcoming
                                .slice(0, 2)
                                .map(orderCard)
                                .join("") ||
                            empty("No upcoming orders")
                        }

                    </div>

                </div>


                <!-- FARM VISIT -->

                <div class="dairy-section">

                    <div
                        class="card farm-home-card"
                        style="
                            background:#ffffff;
                            color:#111111;
                            border:1px solid #e5e7eb;
                        "
                    >

                        <div
                            style="
                                font-size:13px;
                                font-weight:700;
                                color:#111111;
                                margin-bottom:6px;
                            "
                        >
                            FARM EXPERIENCE
                        </div>

                        <h3
                            style="
                                margin:0 0 8px;
                                color:#111111;
                            "
                        >
                            Spend a fun farm day with us.
                        </h3>

                        <p
                            style="
                                color:#111111;
                                line-height:1.5;
                            "
                        >
                            Meet our farmers, see the cows and
                            experience how your milk is produced.
                        </p>

                        <button
                            class="btn btn-primary"
                            data-view="farm"
                        >
                            Book Farm Visit
                        </button>

                    </div>

                </div>


                <!-- REFER A FRIEND -->

                <div class="dairy-section">

                    <div
                        class="card referral-card"
                        style="
                            background:#ffffff;
                            color:#111111;
                            border:1px solid #e5e7eb;
                        "
                    >

                        <div
                            style="
                                font-size:13px;
                                font-weight:700;
                                color:#111111;
                                margin-bottom:6px;
                            "
                        >
                            LOVE WHAT WE DO?
                        </div>

                        <h3
                            style="
                                margin:0 0 8px;
                                color:#111111;
                            "
                        >
                            Refer a Friend
                        </h3>

                        <p
                            style="
                                color:#111111;
                                line-height:1.5;
                            "
                        >
                            Invite your friends to join our dairy
                            family and earn rewards when they purchase.
                        </p>

                        <button
                            class="btn btn-primary"
                            onclick="referFriend()"
                        >
                            Refer a Friend
                        </button>

                    </div>

                </div>


                ${nav("home")}

            </div>
        `;
    }


    /* ---------------------------------------------------------
       PRODUCTS
    --------------------------------------------------------- */

    function filteredProducts() {

        let products = [...S.products];

        if (S.search.trim()) {

            const search = S.search.toLowerCase();

            products = products.filter((product) => {

                const text = [
                    product.name,
                    product.item_name,
                    product.item_group,
                    product.description
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();

                return text.includes(search);
            });
        }

        if (S.category !== "All") {

            products = products.filter((product) => {

                const text = [
                    product.item_group,
                    product.category,
                    product.item_name,
                    product.name
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();

                return text.includes(S.category.toLowerCase());
            });
        }

        return products;
    }


    function products() {

        const list = filteredProducts();

        return `
            <div
                class="dairy-products"
                style="
                    background:#ffffff;
                    color:#111111;
                "
            >

                ${header(
                    "Products",
                    "Fresh dairy products"
                )}


                <!-- DAIRY / NON DAIRY -->

                <div
                    class="product-main-tabs"
                    style="
                        display:flex;
                        justify-content:center;
                        gap:30px;
                        border-bottom:1px solid #e5e7eb;
                        padding:4px 0 12px;
                    "
                >

                    <button
                        class="chip ${
                            S.productTab === "Dairy"
                                ? "active"
                                : ""
                        }"
                        style="color:#111111;"
                        onclick="setProductTab('Dairy')"
                    >
                        🥛 Dairy
                    </button>

                    <button
                        class="chip ${
                            S.productTab === "Non-Dairy"
                                ? "active"
                                : ""
                        }"
                        style="color:#111111;"
                        onclick="setProductTab('Non-Dairy')"
                    >
                        🧃 Non-Dairy
                    </button>

                </div>


                <!-- SEARCH -->

                <div class="dairy-section">

                    <input
                        id="product-search"
                        value="${esc(S.search)}"
                        style="
                            width:100%;
                            box-sizing:border-box;
                            padding:14px;
                            border:1px solid #dfe5e1;
                            border-radius:12px;
                            background:#ffffff;
                            color:#111111;
                            font-size:15px;
                        "
                        placeholder="Search milk, curd, paneer..."
                    >

                </div>


                <!-- PRODUCTS -->

                <div class="dairy-section">

                    <div
                        style="
                            display:grid;
                            grid-template-columns:125px minmax(0,1fr);
                            gap:12px;
                            align-items:start;
                        "
                    >

                        <!-- CATEGORY -->

                        <div>

                            <div
                                class="card"
                                style="
                                    position:sticky;
                                    top:8px;
                                    background:#ffffff;
                                    border:1px solid #e5e7eb;
                                    padding:10px;
                                "
                            >

                                ${
                                    categories
                                        .map((category) => `
                                            <button
                                                class="chip ${
                                                    S.category === category
                                                        ? "active"
                                                        : ""
                                                }"
                                                style="
                                                    color:#111111;
                                                    width:100%;
                                                    margin-bottom:8px;
                                                    white-space:normal;
                                                "
                                                onclick="setCategory('${esc(category)}')"
                                            >
                                                ${esc(category)}
                                            </button>
                                        `)
                                        .join("")
                                }

                            </div>

                        </div>


                        <!-- LIST -->

                        <div>

                            ${
                                list.length
                                    ? list
                                        .map((product) =>
                                            productCard(product, {
                                                subscribe: true
                                            })
                                        )
                                        .join("")
                                    : empty("No products found")
                            }

                        </div>

                    </div>

                </div>


                ${nav("products")}

            </div>
        `;
    }


    /* ---------------------------------------------------------
       OFFERS
    --------------------------------------------------------- */

    function offers() {

        return `
            ${header(
                "Offers",
                "Special prices for you"
            )}

            <div class="dairy-section">

                <div
                    class="chips"
                    style="
                        display:flex;
                        gap:8px;
                        flex-wrap:wrap;
                    "
                >

                    ${
                        ["All", "Milk", "Paneer", "Ghee", "Other"]
                            .map((category, index) => `
                                <span
                                    class="chip ${index === 0 ? "active" : ""}"
                                    style="color:#111111;"
                                >
                                    ${category}
                                </span>
                            `)
                            .join("")
                    }

                </div>

            </div>


            <div class="dairy-section">

                ${
                    S.offers
                        .map(offerCard)
                        .join("") ||
                    empty("No active offers")
                }

            </div>

            ${nav("offers")}
        `;
    }


    /* ---------------------------------------------------------
       ORDERS
    --------------------------------------------------------- */

    function orders() {

        return `
            ${header(
                "My Orders",
                "Manage your dairy deliveries"
            )}

            <div class="dairy-section">

                <div
                    class="chips"
                    style="
                        display:flex;
                        gap:8px;
                    "
                >

                    <button
                        class="chip ${
                            S.orderTab === "upcoming"
                                ? "active"
                                : ""
                        }"
                        style="color:#111111;"
                        onclick="setOrderTab('upcoming')"
                    >
                        Upcoming
                    </button>

                    <button
                        class="chip ${
                            S.orderTab === "delivered"
                                ? "active"
                                : ""
                        }"
                        style="color:#111111;"
                        onclick="setOrderTab('delivered')"
                    >
                        Delivered
                    </button>

                </div>


                ${
                    S.orderTab === "upcoming"
                        ? `
                            <div style="margin-top:16px;">
                                ${
                                    S.upcoming
                                        .map(orderCard)
                                        .join("") ||
                                    empty("No upcoming orders")
                                }
                            </div>
                          `
                        : `
                            <div style="margin-top:16px;">
                                ${
                                    S.delivered
                                        .map((order) => `
                                            <div
                                                class="card"
                                                style="
                                                    color:#111111;
                                                    background:#ffffff;
                                                    border:1px solid #e5e7eb;
                                                    margin-bottom:10px;
                                                "
                                            >

                                                <b style="color:#111111;">
                                                    ${esc(
                                                        order.item_summary ||
                                                        order.name
                                                    )}
                                                </b>

                                                <div
                                                    class="dairy-sub"
                                                    style="color:#111111;"
                                                >
                                                    Delivered at
                                                    ${esc(
                                                        order.delivered_at ||
                                                        order.delivery_date ||
                                                        "—"
                                                    )}
                                                </div>

                                                ${
                                                    order.proof_of_delivery
                                                        ? `
                                                            <div style="margin-top:8px;">
                                                                <a
                                                                    href="${esc(order.proof_of_delivery)}"
                                                                    target="_blank"
                                                                    style="color:#111111;"
                                                                >
                                                                    View Proof of Delivery
                                                                </a>
                                                            </div>
                                                          `
                                                        : `
                                                            <div
                                                                style="
                                                                    margin-top:8px;
                                                                    color:#111111;
                                                                "
                                                            >
                                                                Proof not uploaded
                                                            </div>
                                                          `
                                                }

                                                <div
                                                    style="
                                                        font-weight:800;
                                                        margin-top:8px;
                                                        color:#111111;
                                                    "
                                                >
                                                    Order Total:
                                                    ${money(order.order_total)}
                                                </div>

                                            </div>
                                        `)
                                        .join("") ||
                                    empty("No delivered orders")
                                }
                            </div>
                          `
                }

            </div>

            ${nav("orders")}
        `;
    }


    /* ---------------------------------------------------------
       FARM
    --------------------------------------------------------- */

    function postCard(post) {

        return `
            <div
                class="card farm-post"
                style="
                    color:#111111;
                    background:#ffffff;
                    border:1px solid #e5e7eb;
                "
            >

                <b style="color:#111111;">
                    ${esc(post.author || "Farm Team")}
                </b>

                <div
                    class="dairy-sub"
                    style="color:#111111;"
                >
                    ${esc(post.creation || "")}
                </div>

                <p style="color:#111111;">
                    ${esc(post.content || "")}
                </p>

                ${
                    post.cover_image
                        ? `
                            <img
                                src="${esc(post.cover_image)}"
                                style="
                                    width:100%;
                                    border-radius:12px;
                                "
                            >
                          `
                        : ""
                }

                <div
                    class="actions"
                    style="
                        display:flex;
                        gap:8px;
                        margin-top:10px;
                    "
                >

                    <button
                        class="btn btn-light"
                        style="color:#111111;"
                        onclick="likePost('${esc(post.name)}')"
                    >
                        ♥ ${post.like_count || 0}
                    </button>

                    <button
                        class="btn btn-light"
                        style="color:#111111;"
                        onclick="commentPost('${esc(post.name)}')"
                    >
                        💬 ${post.comment_count || 0}
                    </button>

                </div>

            </div>
        `;
    }


    function farm() {

        return `
            ${header(
                "Farm Visit",
                "Experience our farms and meet our farmers"
            )}

            <div class="dairy-section">

                <button
                    class="btn btn-primary"
                    onclick="showBooking()"
                >
                    Book Farm Visit
                </button>

            </div>


            <div class="dairy-section">

                <div
                    class="hero"
                    style="color:#111111;"
                >

                    <b
                        style="
                            font-size:25px;
                            color:#111111;
                        "
                    >
                        Real Farms. Real Food.
                    </b>

                    <p style="color:#111111;">
                        See our cows, farms and how your milk
                        is produced.
                    </p>

                </div>

            </div>


            <div class="dairy-section">

                <h3 style="color:#111111;">
                    Upcoming Visits
                </h3>

                ${empty("No upcoming visit yet.")}

            </div>


            <div class="dairy-section">

                <div
                    style="
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                    "
                >

                    <h3 style="color:#111111;">
                        Farm Posts
                    </h3>

                    <button
                        class="btn btn-light"
                        style="color:#111111;"
                        onclick="showPostForm()"
                    >
                        + Add Post
                    </button>

                </div>

                <div style="margin-top:12px;">

                    ${
                        S.posts
                            .map(postCard)
                            .join("") ||
                        empty("No farm posts yet")
                    }

                </div>

            </div>


            ${nav("")}
        `;
    }


    /* ---------------------------------------------------------
       ACCOUNT
    --------------------------------------------------------- */

    function account() {

        return `
            ${header(
                "Account",
                "Profile, wallet and invoices"
            )}

            <div class="dairy-section">

                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <b style="color:#111111;">
                        Customer Profile
                    </b>

                    <p
                        class="dairy-sub"
                        style="color:#111111;"
                    >
                        Profile, address and payment methods
                    </p>

                </div>


                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <b style="color:#111111;">
                        Wallet
                    </b>

                    <div
                        class="price"
                        style="color:#111111;"
                    >
                        ${money(S.wallet)}
                    </div>

                    <button
                        class="btn btn-primary"
                        onclick="openAddMoney()"
                    >
                        + Add Money
                    </button>

                </div>


                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <b style="color:#111111;">
                        Invoices
                    </b>

                    <p
                        class="dairy-sub"
                        style="color:#111111;"
                    >
                        Order and subscription invoices
                    </p>

                    <button
                        class="btn btn-light"
                        style="color:#111111;"
                        onclick="showInvoices()"
                    >
                        View Invoices
                    </button>

                </div>


                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <b style="color:#111111;">
                        Farm Visits
                    </b>

                    <p
                        class="dairy-sub"
                        style="color:#111111;"
                    >
                        Bookings and visit history
                    </p>

                    <button
                        class="btn btn-light"
                        style="color:#111111;"
                        data-view="farm"
                    >
                        View Farm Visits
                    </button>

                </div>

            </div>

            ${nav("account")}
        `;
    }


    /* ---------------------------------------------------------
       ACTIONS
    --------------------------------------------------------- */

    window.setHomeTab = (tab) => {
        S.homeTab = tab;
        render();
    };


    window.setCategory = (category) => {
        S.category = category;
        render();
    };


    window.setProductTab = (tab) => {
        S.productTab = tab;
        render();
    };


    window.setOrderTab = (tab) => {
        S.orderTab = tab;
        render();
    };


    window.addProduct = (product) => {
        toast("Product added to cart");
        console.log("Add product:", product);
    };


    window.subscribeProduct = (product) => {
        toast("Subscription selected");
        console.log("Subscribe:", product);
    };


    window.addItemsToOrder = (order) => {
        toast("Open Products to add items");
        S.view = "products";
        render();
    };


    window.openAddMoney = () => {
        toast("Payment gateway will be connected here");
    };


    window.referFriend = () => {
        toast("Referral sharing will be connected here");
    };


    /* ---------------------------------------------------------
       FARM BOOKING
    --------------------------------------------------------- */

    window.showBooking = () => {

        root.innerHTML = `
            ${header(
                "Book Farm Visit",
                "Choose your visit date and guests"
            )}

            <div class="dairy-section">

                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <div class="form-row">

                        <label style="color:#111111;">
                            Select Date
                        </label>

                        <input
                            id="visit-date"
                            type="date"
                        >

                    </div>


                    <div class="form-row">

                        <label style="color:#111111;">
                            Number of Guests
                        </label>

                        <input
                            id="visit-guests"
                            type="number"
                            min="1"
                            value="2"
                        >

                    </div>


                    <div class="form-row">

                        <label style="color:#111111;">
                            Special Request
                        </label>

                        <textarea
                            id="visit-note"
                        ></textarea>

                    </div>


                    <button
                        class="btn btn-primary"
                        onclick="submitVisit()"
                    >
                        Continue to Payment
                    </button>

                </div>

            </div>

            ${nav("farm")}
        `;

        bindNavigation();
    };


    window.submitVisit = async () => {

        try {

            const response = await api(
                "book_farm_visit",
                {
                    visit_date:
                        document.getElementById("visit-date").value,

                    guests:
                        document.getElementById("visit-guests").value,

                    special_request:
                        document.getElementById("visit-note").value
                }
            );

            if (response.message?.payment_required) {

                location.href =
                    "/payment-request?reference=" +
                    encodeURIComponent(
                        response.message.name
                    );

                return;
            }

            toast("Farm visit booked");

            await load();

            S.view = "farm";

            render();

        } catch (error) {

            console.error(error);

            toast("Unable to book farm visit");
        }
    };


    window.likePost = async (post) => {

        try {

            await api("like_post", {
                post
            });

            await load();

            S.view = "farm";

            render();

        } catch (error) {

            console.error(error);

            toast("Unable to like post");
        }
    };


    window.commentPost = async (post) => {

        const comment = prompt(
            "Write your comment"
        );

        if (!comment) {
            return;
        }

        try {

            await api(
                "add_comment",
                {
                    post,
                    comment
                }
            );

            await load();

            S.view = "farm";

            render();

        } catch (error) {

            console.error(error);

            toast("Unable to add comment");
        }
    };


    window.showPostForm = () => {

        root.innerHTML = `
            ${header(
                "Create Post",
                "Share your farm experience"
            )}

            <div class="dairy-section">

                <div
                    class="card"
                    style="
                        color:#111111;
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                    "
                >

                    <div class="form-row">

                        <label style="color:#111111;">
                            Post
                        </label>

                        <textarea
                            id="post-content"
                            rows="6"
                            placeholder="Share your farm visit experience..."
                        ></textarea>

                    </div>


                    <div class="form-row">

                        <label style="color:#111111;">
                            Photo URL
                        </label>

                        <input
                            id="post-image"
                        >

                    </div>


                    <button
                        class="btn btn-primary"
                        onclick="createPost()"
                    >
                        Post
                    </button>

                </div>

            </div>

            ${nav("farm")}
        `;

        bindNavigation();
    };


    window.createPost = async () => {

        try {

            await api(
                "create_farm_post",
                {
                    content:
                        document.getElementById(
                            "post-content"
                        ).value,

                    cover_image:
                        document.getElementById(
                            "post-image"
                        ).value
                }
            );

            await load();

            S.view = "farm";

            render();

        } catch (error) {

            console.error(error);

            toast("Unable to create post");
        }
    };


    window.toggleOrder = async (
        order,
        action
    ) => {

        try {

            await api(
                "pause_resume_order",
                {
                    order,
                    action
                }
            );

            await load();

            render();

        } catch (error) {

            console.error(error);

            toast("Unable to update order");
        }
    };


    /* ---------------------------------------------------------
       INVOICES
    --------------------------------------------------------- */

    window.showInvoices = async () => {

        try {

            const response =
                await api("invoices");

            root.innerHTML = `
                ${header(
                    "Invoices",
                    "Order and subscription invoices"
                )}

                <div class="dairy-section">

                    ${
                        (response.message || [])
                            .map((invoice) => `
                                <div
                                    class="card"
                                    style="
                                        color:#111111;
                                        background:#ffffff;
                                        border:1px solid #e5e7eb;
                                    "
                                >

                                    <b style="color:#111111;">
                                        ${esc(invoice.name)}
                                    </b>

                                    <div
                                        style="
                                            color:#111111;
                                            margin-top:5px;
                                        "
                                    >
                                        ${esc(
                                            invoice.posting_date ||
                                            ""
                                        )}
                                    </div>

                                    <div
                                        class="price"
                                        style="color:#111111;"
                                    >
                                        ${money(
                                            invoice.grand_total
                                        )}
                                    </div>

                                    <div
                                        class="dairy-sub"
                                        style="color:#111111;"
                                    >
                                        ${esc(
                                            invoice.status ||
                                            ""
                                        )}
                                    </div>

                                </div>
                            `)
                            .join("") ||
                        empty("No invoices")
                    }

                </div>

                ${nav("account")}
            `;

            bindNavigation();

        } catch (error) {

            console.error(error);

            toast("Unable to load invoices");
        }
    };


    /* ---------------------------------------------------------
       SEARCH
    --------------------------------------------------------- */

    const bindSearch = () => {

        const input =
            document.getElementById(
                "product-search"
            );

        if (!input) {
            return;
        }

        input.oninput = (event) => {

            S.search =
                event.target.value;

            const productsRoot =
                document.querySelector(
                    ".dairy-products"
                );

            if (!productsRoot) {
                return;
            }

            render();
        };
    };


    /* ---------------------------------------------------------
       LOAD DATA
    --------------------------------------------------------- */

    async function load() {

        try {

            const [
                productsResponse,
                offersResponse,
                upcomingResponse,
                deliveredResponse,
                walletResponse,
                farmResponse
            ] = await Promise.all([
                api("products"),
                api("offers"),
                api("upcoming_orders"),
                api("delivered_orders"),
                api("wallet"),
                api("farm_posts")
            ]);

            S.products =
                productsResponse.message || [];

            S.offers =
                offersResponse.message || [];

            S.upcoming =
                upcomingResponse.message || [];

            S.delivered =
                deliveredResponse.message || [];

            S.wallet =
                walletResponse.message?.balance || 0;

            S.posts =
                farmResponse.message || [];

        } catch (error) {

            console.error(
                "Dairy App data loading error:",
                error
            );

        }

        render();
    }


    /* ---------------------------------------------------------
       RENDER
    --------------------------------------------------------- */

    function render() {

        if (S.view === "home") {
            root.innerHTML = home();
        }

        else if (S.view === "products") {
            root.innerHTML = products();
        }

        else if (S.view === "orders") {
            root.innerHTML = orders();
        }

        else if (S.view === "offers") {
            root.innerHTML = offers();
        }

        else if (S.view === "farm") {
            root.innerHTML = farm();
        }

        else if (S.view === "account") {
            root.innerHTML = account();
        }

        else {
            root.innerHTML = home();
        }

        bindNavigation();
        bindSearch();
    }


    /* ---------------------------------------------------------
       START
    --------------------------------------------------------- */

    load();

})();
