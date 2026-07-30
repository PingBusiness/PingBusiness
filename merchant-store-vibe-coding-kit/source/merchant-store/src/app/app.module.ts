import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { AccountComponent } from './account/account.component';
import { CartComponent } from './cart/cart.component';
import { CatalogComponent } from './catalog/catalog.component';
import { CheckoutComponent } from './checkout/checkout.component';
import { HeaderComponent } from './components/header/header.component';
import { InputFieldComponent } from './components/input-field/input-field.component';
import { MessageComponent } from './components/message/message.component';
import { ProductCardComponent } from './components/product-card/product-card.component';
import { ToastComponent } from './components/toast/toast.component';
import { HomeComponent } from './home/home.component';
import { OrderDetailComponent } from './order-detail/order-detail.component';
import { OrdersComponent } from './orders/orders.component';
import { ProductComponent } from './product/product.component';
import { SigninComponent } from './signin/signin.component';
import { SignupComponent } from './signup/signup.component';
import { SubscriptionsComponent } from './subscriptions/subscriptions.component';
import { SubscriptionCheckoutComponent } from './subscription-checkout/subscription-checkout.component';

@NgModule({
  declarations: [
    AppComponent,
    AccountComponent,
    CartComponent,
    CatalogComponent,
    CheckoutComponent,
    HeaderComponent,
    HomeComponent,
    InputFieldComponent,
    MessageComponent,
    OrderDetailComponent,
    OrdersComponent,
    ProductCardComponent,
    ProductComponent,
    ToastComponent,
    SigninComponent,
    SignupComponent,
    SubscriptionCheckoutComponent,
    SubscriptionsComponent
  ],
  imports: [
    BrowserModule,
    FormsModule,
    HttpClientModule,
    AppRoutingModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule {}
